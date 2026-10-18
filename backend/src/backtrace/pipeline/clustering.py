"""Symptom clustering (§8.2 step 6): L2-normalized embeddings reduced by
PCA, optionally augmented with a weighted product/region one-hot, then
clustered with HDBSCAN."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import Complaint, ComplaintEmbedding, SymptomCluster, SymptomClusterMember
from backtrace.llm.config import ClusterParams


def structured_matrix(products: Sequence[str], regions: Sequence[str]) -> np.ndarray:
    product_cats = sorted(set(products))
    region_cats = sorted(set(regions))
    product_index = {p: i for i, p in enumerate(product_cats)}
    region_index = {r: i for i, r in enumerate(region_cats)}

    out = np.zeros((len(products), len(product_cats) + len(region_cats)), dtype=float)
    for row, (product, region) in enumerate(zip(products, regions)):
        out[row, product_index[product]] = 1.0
        out[row, len(product_cats) + region_index[region]] = 1.0
    return out


def cluster_symptoms(vectors: np.ndarray, *, params: ClusterParams, structured: np.ndarray | None = None) -> np.ndarray:
    n, d = vectors.shape
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / np.where(norms == 0, 1.0, norms)

    n_components = max(1, min(params.pca_dims, n - 1, d))
    reduced = PCA(n_components=n_components, random_state=params.seed).fit_transform(normalized)
    if structured is not None:
        reduced = np.hstack([reduced, params.structured_weight * structured])

    return HDBSCAN(min_cluster_size=params.min_cluster_size, min_samples=params.min_samples).fit_predict(reduced)


def run_clustering_stage(session_factory: sessionmaker, run_id: str, params: ClusterParams) -> dict:
    with session_factory() as session:
        rows = session.execute(
            select(Complaint.complaint_id, Complaint.product, Complaint.region, ComplaintEmbedding.embedding)
            .join(ComplaintEmbedding, ComplaintEmbedding.complaint_id == Complaint.complaint_id)
            .where(ComplaintEmbedding.run_id == run_id)
            .order_by(Complaint.complaint_id)
        ).all()

        complaint_ids = [row[0] for row in rows]
        labels = np.empty(0, dtype=int)
        if rows:
            structured = structured_matrix([row[1] for row in rows], [row[2] for row in rows])
            vectors = np.array([row[3] for row in rows], dtype=float)
            labels = cluster_symptoms(vectors, params=params, structured=structured)

        session.execute(delete(SymptomClusterMember).where(SymptomClusterMember.run_id == run_id))
        session.execute(delete(SymptomCluster).where(SymptomCluster.run_id == run_id))

        cluster_ids: dict[int, str] = {}
        for label in sorted(int(label) for label in set(labels.tolist()) if label != -1):
            cluster_id = f"cluster-{run_id}-{label}"
            cluster_ids[label] = cluster_id
            session.add(
                SymptomCluster(
                    id=cluster_id,
                    run_id=run_id,
                    label=label,
                    size=int((labels == label).sum()),
                    method="text+structured",
                )
            )

        for complaint_id, label in zip(complaint_ids, labels.tolist()):
            session.add(
                SymptomClusterMember(
                    run_id=run_id,
                    complaint_id=complaint_id,
                    cluster_id=cluster_ids.get(label) if label != -1 else None,
                )
            )
        session.commit()

    return {"clusters": len(cluster_ids), "noise": int((labels == -1).sum())}
