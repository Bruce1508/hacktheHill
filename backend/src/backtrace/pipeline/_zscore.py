"""Zero-variance-safe z-score shared by the anomaly and burst stages."""

import math


def zscore(mean: float, std: float, value: float) -> float:
    if std < 1e-9:
        if value == mean:
            return 0.0
        return math.inf if value > mean else -math.inf
    return (value - mean) / std
