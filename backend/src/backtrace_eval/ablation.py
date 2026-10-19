"""Ablation A/B/C (§13.3): does adding structured features (B) or the full
evidence-linking pipeline (C) improve on text-only clustering (A)?"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict
from typing import Sequence

import numpy as np
from sklearn.metrics import adjusted_rand_score, completeness_score, homogeneity_score, normalized_mutual_info_score
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import CohortMember, Complaint, ComplaintEmbedding
from backtrace.db.session import make_session_factory
from backtrace.llm.config import ClusterParams, PipelineConfig
from backtrace.pipeline.clustering import cluster_symptoms, structured_matrix
from backtrace_eval.db.models import GoldComplaintLabel


def _singleton_fill(labels: Sequence[str | None], prefix: str) -> list[str]:
    filled = []
    counter = 0
    for label in labels:
        if label is None:
            filled.append(f"{prefix}{counter}")
            counter += 1
        else:
            filled.append(label)
    return filled


def clustering_metrics(true: Sequence[str | None], pred: Sequence[str | None]) -> dict[str, float]:
    true_filled = _singleton_fill(true, "__true_singleton_")
    pred_filled = _singleton_fill(pred, "__pred_singleton_")

    groups: dict[str, list[str | None]] = {}
    for t, p in zip(true, pred):
        if p is not None:
            groups.setdefault(p, []).append(t)

    eligible = [members for members in groups.values() if len(members) >= 5]
    false_merges = 0
    for members in eligible:
        counts = Counter(members).most_common()
        if len(counts) >= 2 and counts[1][1] / len(members) >= 0.2:
            false_merges += 1
    false_merge_rate = false_merges / len(eligible) if eligible else 0.0

    true_causes = {t for t in true if t is not None}
    cause_recall_hits = sum(
        1
        for cause in true_causes
        if any(sum(1 for t in members if t == cause) / len(members) >= 0.8 for members in groups.values())
    )
    cause_recall = cause_recall_hits / len(true_causes) if true_causes else 1.0

    return {
        "ari": adjusted_rand_score(true_filled, pred_filled),
        "nmi": normalized_mutual_info_score(true_filled, pred_filled),
        "homogeneity": homogeneity_score(true_filled, pred_filled),
        "completeness": completeness_score(true_filled, pred_filled),
        "false_merge_rate": false_merge_rate,
        "cause_recall": cause_recall,
    }


def run_ablation(database_url_eval: str, run_id: str, params: ClusterParams) -> dict[str, dict[str, float]]:
    session_factory: sessionmaker = make_session_factory(database_url_eval)
    with session_factory() as session:
        rows = session.execute(
            select(Complaint.complaint_id, Complaint.product, Complaint.region, ComplaintEmbedding.embedding)
            .join(ComplaintEmbedding, ComplaintEmbedding.complaint_id == Complaint.complaint_id)
            .where(ComplaintEmbedding.run_id == run_id)
            .order_by(Complaint.complaint_id)
        ).all()
        if not rows:
            raise ValueError(f"no complaint embeddings found for run_id={run_id!r}")

        complaint_ids = [row[0] for row in rows]
        vectors = np.array([row[3] for row in rows], dtype=float)

        true_by_id = dict(
            session.execute(
                select(GoldComplaintLabel.complaint_id, GoldComplaintLabel.root_cause_id).where(
                    GoldComplaintLabel.complaint_id.in_(complaint_ids)
                )
            ).all()
        )
        true = [true_by_id.get(cid) for cid in complaint_ids]

        cohort_by_id = dict(
            session.execute(
                select(CohortMember.complaint_id, CohortMember.cohort_id).where(CohortMember.run_id == run_id)
            ).all()
        )

    labels_a = cluster_symptoms(vectors, params=params)
    pred_a = [None if label == -1 else f"cluster-{label}" for label in labels_a.tolist()]

    structured = structured_matrix([row[1] for row in rows], [row[2] for row in rows])
    labels_b = cluster_symptoms(vectors, params=params, structured=structured)
    pred_b = [None if label == -1 else f"cluster-{label}" for label in labels_b.tolist()]

    pred_c = [cohort_by_id.get(cid) for cid in complaint_ids]

    return {
        "A": clustering_metrics(true, pred_a),
        "B": clustering_metrics(true, pred_b),
        "C": clustering_metrics(true, pred_c),
    }


def _config_hash(params: ClusterParams) -> str:
    return hashlib.sha256(json.dumps(asdict(params), sort_keys=True).encode()).hexdigest()[:12]


def _render_report(run_id: str, params: ClusterParams, results: dict[str, dict[str, float]]) -> str:
    metrics = ("ari", "nmi", "homogeneity", "completeness", "false_merge_rate", "cause_recall")
    lines = [
        f"# Ablation report — {run_id}",
        "",
        f"- config hash: `{_config_hash(params)}`",
        f"- seed: `{params.seed}`",
        f"- date: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        "",
        "| variant | " + " | ".join(metrics) + " |",
        "| --- | " + " | ".join("---" for _ in metrics) + " |",
    ]
    for variant, scores in results.items():
        lines.append(f"| {variant} | " + " | ".join(f"{scores[m]:.3f}" for m in metrics) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    database_url_eval = os.environ["DATABASE_URL_EVAL"]
    params = PipelineConfig.load().clustering
    results = run_ablation(database_url_eval, args.run_id, params)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(_render_report(args.run_id, params, results))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
