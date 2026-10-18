from backtrace.llm.config import PipelineConfig


def test_pipeline_config_loads_day3_sections_from_yaml():
    config = PipelineConfig.load()

    assert config.anomaly.window_points == 48
    assert config.anomaly.z_threshold == 4.0
    assert config.anomaly.min_points == 2
    assert config.anomaly.metrics == ("packet_loss_pct", "errored_seconds", "optical_power_dbm")

    assert config.burst.bucket_minutes == 15
    assert config.burst.baseline_buckets == 96
    assert config.burst.z_threshold == 3.0
    assert config.burst.min_count == 5

    assert config.clustering.pca_dims == 20
    assert config.clustering.min_cluster_size == 15
    assert config.clustering.min_samples == 5
    assert config.clustering.structured_weight == 0.5
    assert config.clustering.seed == 20261017

    assert config.linking.threshold == 3.5
    assert config.linking.ambiguity_margin == 0.5
    assert config.linking.lag_max_minutes == 720
    assert config.linking.temporal_tau_minutes == 180


def test_linking_semantic_weight_is_the_lowest_weight():
    # Encodes the T2 constraint (telemetry/structure matter more than raw
    # text similarity) in config, not just in a comment.
    config = PipelineConfig.load()
    weights = config.linking.weights
    assert weights["semantic"] < min(w for name, w in weights.items() if name != "semantic")
