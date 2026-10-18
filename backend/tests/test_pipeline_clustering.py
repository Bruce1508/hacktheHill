import os

import numpy as np
from sqlalchemy import text

from backtrace.db.session import get_session, make_session_factory
from backtrace.llm.config import ClusterParams, PipelineConfig
from backtrace.pipeline.clustering import cluster_symptoms, run_clustering_stage, structured_matrix

PARAMS = ClusterParams(pca_dims=10, min_cluster_size=15, min_samples=5, structured_weight=0.5, seed=42)


def _blobs(rng: np.random.Generator, n_per_blob: int = 60, n_outliers: int = 10, dim: int = 768) -> np.ndarray:
    centers = rng.normal(scale=20.0, size=(3, dim))
    blobs = [center + rng.normal(scale=0.5, size=(n_per_blob, dim)) for center in centers]

    # A random direction in 768-d is *nearly* orthogonal to the blob centers but not
    # exactly, so a handful would otherwise fall inside a blob's PCA-reduced boundary.
    # Explicitly strip the blob-center components so outliers land in genuinely
    # separate territory instead of near the shared centroid.
    basis = centers / np.linalg.norm(centers, axis=1, keepdims=True)
    raw_outliers = rng.normal(scale=20.0, size=(n_outliers, dim))
    outliers = raw_outliers - raw_outliers @ basis.T @ basis
    return np.vstack(blobs + [outliers])


def test_three_well_separated_blobs_cluster_purely():
    rng = np.random.default_rng(0)
    vectors = _blobs(rng)

    labels = cluster_symptoms(vectors, params=PARAMS)

    blob_labels = labels[:180].reshape(3, 60)
    for row in blob_labels:
        assert len(set(row.tolist())) == 1
        assert row[0] != -1
    assert len({blob_labels[0, 0], blob_labels[1, 0], blob_labels[2, 0]}) == 3
    assert (labels[180:] == -1).sum() >= 5


def test_fewer_points_than_min_samples_is_all_noise_not_a_crash():
    rng = np.random.default_rng(3)
    vectors = rng.normal(size=(PARAMS.min_samples - 1, 768))

    labels = cluster_symptoms(vectors, params=PARAMS)

    assert (labels == -1).all()


def test_clustering_is_deterministic_for_the_same_input():
    rng = np.random.default_rng(1)
    vectors = _blobs(rng)

    first = cluster_symptoms(vectors, params=PARAMS)
    second = cluster_symptoms(vectors, params=PARAMS)

    assert first.tolist() == second.tolist()


def test_structured_features_separate_blobs_overlapping_in_vector_space():
    rng = np.random.default_rng(2)
    center = rng.normal(scale=20.0, size=768)
    vectors = np.vstack(
        [
            center + rng.normal(scale=0.5, size=(60, 768)),
            center + rng.normal(scale=0.5, size=(60, 768)),
        ]
    )
    products = ["isp"] * 120
    regions = ["north"] * 60 + ["south"] * 60

    without_structured = cluster_symptoms(vectors, params=PARAMS)
    labels_seen = set(without_structured.tolist()) - {-1}
    assert len(labels_seen) < 2, "overlapping blobs should not separate on vectors alone"

    structured = structured_matrix(products, regions)
    with_structured = cluster_symptoms(vectors, params=PARAMS, structured=structured)
    north_labels = set(with_structured[:60].tolist()) - {-1}
    south_labels = set(with_structured[60:].tolist()) - {-1}
    assert north_labels, "north blob should form its own cluster once region is encoded"
    assert south_labels, "south blob should form its own cluster once region is encoded"
    assert north_labels.isdisjoint(south_labels)


def test_run_clustering_stage_is_idempotent():
    pipeline_url = os.environ["DATABASE_URL_PIPELINE"]
    run_id = "dev-run-2"  # already has complaint_features + embeddings loaded (dev fixture)
    params = PipelineConfig.load().clustering
    session_factory = make_session_factory(pipeline_url)

    try:
        first = run_clustering_stage(session_factory, run_id, params)
        second = run_clustering_stage(session_factory, run_id, params)
        assert first == second

        with get_session(pipeline_url) as session:
            n_embeddings = session.execute(
                text("SELECT count(*) FROM app.complaint_embeddings WHERE run_id = :rid"), {"rid": run_id}
            ).scalar_one()
            n_members = session.execute(
                text("SELECT count(*) FROM app.symptom_cluster_members WHERE run_id = :rid"), {"rid": run_id}
            ).scalar_one()
            assert n_members == n_embeddings
    finally:
        with get_session(pipeline_url) as session:
            session.execute(text("DELETE FROM app.symptom_cluster_members WHERE run_id = :rid"), {"rid": run_id})
            session.execute(text("DELETE FROM app.symptom_clusters WHERE run_id = :rid"), {"rid": run_id})
            session.commit()
