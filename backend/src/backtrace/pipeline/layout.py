"""Deterministic provisional 2D layout from a run's embeddings (§Phase 5).
PCA via numpy.linalg.svd — two components is a few lines of linear algebra,
not worth a scikit-learn dependency. Recomputes the full embedding set every
run rather than laying out only new complaints: PCA's projection basis
depends on the whole dataset, so an incremental update would silently drift
the coordinate system between partial runs."""

from __future__ import annotations

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from backtrace.db.models import ComplaintEmbedding, ComplaintLayout

LAYOUT_VERSION = "pca-svd-v1"


def _pca_2d(vectors: np.ndarray) -> np.ndarray:
    centered = vectors - vectors.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:2]
    if components.shape[0] < 2:  # fewer rows than components (e.g. a single-complaint run)
        components = np.vstack([components, np.zeros((2 - components.shape[0], components.shape[1]))])
    return centered @ components.T


def run_layout_stage(session_factory: sessionmaker, run_id: str) -> dict:
    with session_factory() as session:
        rows = session.execute(
            select(ComplaintEmbedding.complaint_id, ComplaintEmbedding.embedding).where(ComplaintEmbedding.run_id == run_id)
        ).all()
        if not rows:
            return {"processed": 0}

        complaint_ids = [row[0] for row in rows]
        vectors = np.asarray([row[1] for row in rows], dtype=np.float64)
        coords = _pca_2d(vectors)

        session.execute(delete(ComplaintLayout).where(ComplaintLayout.run_id == run_id))
        session.add_all(
            ComplaintLayout(run_id=run_id, complaint_id=cid, x=float(x), y=float(y), layout_version=LAYOUT_VERSION)
            for cid, (x, y) in zip(complaint_ids, coords)
        )
        session.commit()
    return {"processed": len(complaint_ids)}
