"""Evidence linking -> cohorts (§8.3): scores each complaint against event
and anomaly candidates across six weighted components, assigns the best
match (or flags it for review), and groups candidates that overlap in time
and region around a shared anomaly into one cohort."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, Sequence

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import (
    Cohort,
    CohortEventLink,
    CohortMember,
    Complaint,
    ComplaintBurst,
    ComplaintEmbedding,
    ComplaintFeatures,
    DetectedAnomaly,
    Event,
    NetworkLink,
    NetworkNode,
    SymptomClusterMember,
)
from backtrace.llm.config import LinkParams
from backtrace.pipeline.burst import Burst

COMPONENTS = ("scope_match", "region_node_overlap", "temporal", "telemetry", "burst", "semantic")


@dataclass(frozen=True)
class Candidate:
    id: str
    kind: Literal["event", "anomaly"]
    start_at: datetime
    end_at: datetime
    region: str | None
    node_ids: frozenset[str]
    customer_ids: frozenset[str] | None


@dataclass(frozen=True)
class ComplaintCtx:
    complaint_id: str
    customer_id: str
    region: str
    node_id: str
    received_at: datetime
    vector: np.ndarray
    cluster_id: str | None


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start <= b_end and b_start <= a_end


def score_components(
    c: ComplaintCtx,
    cand: Candidate,
    *,
    anomalies: Sequence[Candidate],
    bursts: Sequence[Burst],
    centroid: np.ndarray | None,
    params: LinkParams,
) -> dict[str, float]:
    scope_match = 1.0 if (
        (cand.customer_ids is not None and c.customer_id in cand.customer_ids)
        or (cand.kind == "anomaly" and c.node_id in cand.node_ids)
    ) else 0.0

    region_node_overlap = 1.0 if cand.region is not None and cand.region == c.region else 0.0

    if cand.start_at <= c.received_at <= cand.end_at:
        temporal = 1.0
    elif c.received_at > cand.end_at:
        lag_minutes = (c.received_at - cand.end_at).total_seconds() / 60.0
        temporal = math.exp(-lag_minutes / params.temporal_tau_minutes) if 0 < lag_minutes <= params.lag_max_minutes else 0.0
    else:
        temporal = 0.0

    if cand.kind == "anomaly":
        telemetry = scope_match
    else:
        telemetry = 1.0 if any(
            c.node_id in a.node_ids and _overlaps(a.start_at, a.end_at, cand.start_at, cand.end_at) for a in anomalies
        ) else 0.0

    burst = 1.0 if any(
        b.region == c.region and _overlaps(b.start_at, b.end_at, cand.start_at, cand.end_at) for b in bursts
    ) else 0.0

    if centroid is None:
        semantic = 0.0
    else:
        denom = float(np.linalg.norm(c.vector) * np.linalg.norm(centroid))
        semantic = max(0.0, float(np.dot(c.vector, centroid)) / denom) if denom > 0 else 0.0

    return {
        "scope_match": scope_match,
        "region_node_overlap": region_node_overlap,
        "temporal": temporal,
        "telemetry": telemetry,
        "burst": burst,
        "semantic": semantic,
    }


def total_score(components: Mapping[str, float], weights: Mapping[str, float]) -> float:
    return sum(components[k] * weights[k] for k in COMPONENTS)


def assign(scores: Mapping[str, float], params: LinkParams) -> tuple[str | None, bool]:
    if not scores:
        return None, False
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_id, best_val = ranked[0]
    if best_val < params.threshold:
        return None, False
    second_val = ranked[1][1] if len(ranked) > 1 else float("-inf")
    return best_id, (best_val - second_val) < params.ambiguity_margin


def group_candidates(cands: Sequence[Candidate]) -> list[frozenset[str]]:
    parent = {c.id: c.id for c in cands}

    def find(x: str) -> str:
        while parent[x] != x:
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for i, a in enumerate(cands):
        for b in cands[i + 1 :]:
            if (
                a.region is not None
                and a.region == b.region
                and _overlaps(a.start_at, a.end_at, b.start_at, b.end_at)
                and (a.kind == "anomaly" or b.kind == "anomaly")
            ):
                union(a.id, b.id)

    groups: dict[str, set[str]] = {}
    for c in cands:
        groups.setdefault(find(c.id), set()).add(c.id)
    return [frozenset(ids) for ids in groups.values()]


def _event_candidates(session) -> list[Candidate]:
    rows = session.execute(select(Event.id, Event.start_at, Event.end_at, Event.scope)).all()
    candidates = []
    for event_id, start_at, end_at, scope in rows:
        customer_ids = frozenset(scope["customer_ids"]) if "customer_ids" in scope else None
        candidates.append(
            Candidate(
                id=f"event-{event_id}",
                kind="event",
                start_at=start_at,
                end_at=end_at,
                region=scope.get("region"),
                node_ids=frozenset(scope.get("node_ids", [])),
                customer_ids=customer_ids,
            )
        )
    return candidates


def _anomaly_candidates(session, run_id: str) -> list[Candidate]:
    nodes_by_id = {n.id: n for n in session.execute(select(NetworkNode)).scalars().all()}
    links_by_id = {l.id: l for l in session.execute(select(NetworkLink)).scalars().all()}

    rows = session.execute(select(DetectedAnomaly).where(DetectedAnomaly.run_id == run_id)).scalars().all()
    candidates = []
    for anomaly in rows:
        if anomaly.node_id is not None:
            region = nodes_by_id[anomaly.node_id].region
            node_ids = frozenset({anomaly.node_id})
        else:
            link = links_by_id[anomaly.link_id]
            region = link.region
            node_ids = frozenset({link.to_node_id})
        candidates.append(
            Candidate(
                id=f"anomaly-{anomaly.id}",
                kind="anomaly",
                start_at=anomaly.start_at,
                end_at=anomaly.end_at,
                region=region,
                node_ids=node_ids,
                customer_ids=None,
            )
        )
    return candidates


def _complaint_contexts(session, run_id: str) -> list[ComplaintCtx]:
    rows = session.execute(
        select(
            Complaint.complaint_id,
            Complaint.customer_id,
            Complaint.region,
            Complaint.node_id,
            Complaint.received_at,
            ComplaintEmbedding.embedding,
            SymptomClusterMember.cluster_id,
        )
        .join(ComplaintFeatures, ComplaintFeatures.complaint_id == Complaint.complaint_id)
        .join(ComplaintEmbedding, ComplaintEmbedding.complaint_id == Complaint.complaint_id)
        .outerjoin(
            SymptomClusterMember,
            (SymptomClusterMember.complaint_id == Complaint.complaint_id)
            & (SymptomClusterMember.run_id == run_id),
        )
        .where(ComplaintFeatures.run_id == run_id, ComplaintEmbedding.run_id == run_id)
    ).all()

    return [
        ComplaintCtx(
            complaint_id=complaint_id,
            customer_id=customer_id,
            region=region,
            node_id=node_id,
            received_at=received_at,
            vector=np.array(embedding, dtype=float),
            cluster_id=cluster_id,
        )
        for complaint_id, customer_id, region, node_id, received_at, embedding, cluster_id in rows
    ]


def _assign_pass(
    complaints: Sequence[ComplaintCtx],
    candidates: Sequence[Candidate],
    *,
    anomaly_candidates: Sequence[Candidate],
    bursts: Sequence[Burst],
    centroids: Mapping[str, np.ndarray],
    weights: Mapping[str, float],
    params: LinkParams,
) -> dict[str, tuple[str | None, bool]]:
    assignments: dict[str, tuple[str | None, bool]] = {}
    for c in complaints:
        scores = {}
        for cand in candidates:
            components = score_components(
                c,
                cand,
                anomalies=anomaly_candidates,
                bursts=bursts,
                centroid=centroids.get(cand.id),
                params=params,
            )
            scores[cand.id] = total_score(components, weights)
        assignments[c.complaint_id] = assign(scores, params)
    return assignments


def run_linking_stage(session_factory: sessionmaker, run_id: str, params: LinkParams) -> dict:
    with session_factory() as session:
        event_cands = _event_candidates(session)
        anomaly_cands = _anomaly_candidates(session, run_id)
        all_cands = event_cands + anomaly_cands
        by_id = {c.id: c for c in all_cands}

        burst_rows = session.execute(select(ComplaintBurst).where(ComplaintBurst.run_id == run_id)).scalars().all()
        bursts = [
            Burst(region=b.region, start_at=b.start_at, end_at=b.end_at, complaint_count=b.complaint_count, peak_score=b.peak_score)
            for b in burst_rows
        ]

        complaints = _complaint_contexts(session, run_id)

        groups = group_candidates(all_cands)
        group_of: dict[str, frozenset[str]] = {cid: g for g in groups for cid in g}

        pass1 = _assign_pass(
            complaints, all_cands, anomaly_candidates=anomaly_cands, bursts=bursts,
            centroids={}, weights=params.weights, params=params,
        )

        group_vectors: dict[frozenset[str], list[np.ndarray]] = {}
        for c in complaints:
            cand_id, _ = pass1[c.complaint_id]
            if cand_id is not None:
                group_vectors.setdefault(group_of[cand_id], []).append(c.vector)
        group_means = {group: np.mean(vectors, axis=0) for group, vectors in group_vectors.items()}
        centroids = {cand_id: group_means[group] for cand_id, group in group_of.items() if group in group_means}

        final = _assign_pass(
            complaints, all_cands, anomaly_candidates=anomaly_cands, bursts=bursts,
            centroids=centroids, weights=params.weights, params=params,
        )

        session.execute(CohortMember.__table__.delete().where(CohortMember.run_id == run_id))
        session.execute(CohortEventLink.__table__.delete().where(CohortEventLink.run_id == run_id))
        session.execute(Cohort.__table__.delete().where(Cohort.run_id == run_id))

        n = 0
        linked = 0
        needs_review = 0
        noise = 0

        members_by_group: dict[frozenset[str], list[tuple[ComplaintCtx, str, float, bool, dict[str, float]]]] = {}
        no_evidence_by_cluster: dict[str, list[ComplaintCtx]] = {}

        for c in complaints:
            cand_id, review = final[c.complaint_id]
            if cand_id is not None:
                group_key = group_of[cand_id]
                components = score_components(c, by_id[cand_id], anomalies=anomaly_cands, bursts=bursts, centroid=centroids.get(cand_id), params=params)
                score = total_score(components, params.weights)
                members_by_group.setdefault(group_key, []).append((c, cand_id, score, review, components))
                linked += 1
                if review:
                    needs_review += 1
            elif c.cluster_id is not None:
                no_evidence_by_cluster.setdefault(c.cluster_id, []).append(c)
            else:
                noise += 1

        for group_key, members in members_by_group.items():
            cohort_id = f"cohort-{run_id}-{n}"
            n += 1
            session.add(Cohort(id=cohort_id, run_id=run_id, kind="linked"))
            for c, cand_id, score, review, _ in members:
                session.add(
                    CohortMember(
                        run_id=run_id, complaint_id=c.complaint_id, cohort_id=cohort_id,
                        membership_score=score, assigned_by="batch", needs_review=review,
                    )
                )

            by_candidate: dict[str, list[tuple[float, dict[str, float]]]] = {}
            for _, cand_id, score, _, components in members:
                by_candidate.setdefault(cand_id, []).append((score, components))
            for cand_id, entries in by_candidate.items():
                cand = by_id[cand_id]
                evidence = {
                    comp: sum(1 for _, components in entries if components[comp] > 0) / len(entries)
                    for comp in COMPONENTS
                }
                session.add(
                    CohortEventLink(
                        cohort_id=cohort_id, run_id=run_id,
                        event_id=cand_id.removeprefix("event-") if cand.kind == "event" else None,
                        anomaly_id=cand_id.removeprefix("anomaly-") if cand.kind == "anomaly" else None,
                        overlap_score=sum(s for s, _ in entries) / len(entries),
                        evidence=evidence,
                    )
                )

        no_evidence = 0
        for cluster_id, members in no_evidence_by_cluster.items():
            cohort_id = f"cohort-{run_id}-{n}"
            n += 1
            session.add(Cohort(id=cohort_id, run_id=run_id, kind="no_linked_evidence"))
            for c in members:
                session.add(
                    CohortMember(
                        run_id=run_id, complaint_id=c.complaint_id, cohort_id=cohort_id,
                        membership_score=0.0, assigned_by="batch", needs_review=False,
                    )
                )
                no_evidence += 1

        session.commit()

    return {"cohorts": n, "linked": linked, "no_evidence": no_evidence, "needs_review": needs_review, "noise": noise}
