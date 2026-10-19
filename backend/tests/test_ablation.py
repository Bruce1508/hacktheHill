from backtrace_eval.ablation import clustering_metrics


def test_perfect_prediction_gives_ari_one_and_no_false_merges():
    true = ["c1"] * 5 + ["c2"] * 5
    pred = ["g1"] * 5 + ["g2"] * 5

    metrics = clustering_metrics(true, pred)

    assert metrics["ari"] == 1.0
    assert metrics["false_merge_rate"] == 0.0


def test_two_causes_merged_into_one_group_counts_as_a_false_merge():
    true = ["c1"] * 5 + ["c2"] * 5
    pred = ["g1"] * 10

    metrics = clustering_metrics(true, pred)

    assert metrics["false_merge_rate"] == 1.0
    assert metrics["homogeneity"] < 1.0


def test_over_split_keeps_homogeneity_but_drops_completeness():
    true = ["c1"] * 10
    pred = ["g1"] * 5 + ["g2"] * 5

    metrics = clustering_metrics(true, pred)

    assert metrics["homogeneity"] == 1.0
    assert metrics["completeness"] < 1.0


def test_noise_complaints_get_singleton_treatment_not_lumped_together():
    true = ["c1", "c1", "c1", "c1", "c1", None, None, None]
    pred = ["g1", "g1", "g1", "g1", "g1", None, None, None]

    metrics = clustering_metrics(true, pred)

    # the 3 noise complaints must not count as one shared predicted cluster
    assert metrics["ari"] == 1.0
