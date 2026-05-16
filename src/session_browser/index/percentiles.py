"""Percentile computation for session-browser anomaly detection.

Provides P90/P95 computation with fallback thresholds for small datasets.
"""

from __future__ import annotations

from typing import Optional


# Fallback thresholds when data is insufficient (< 20 rows)
# Fixed thresholds — percentile-based computation is unreliable on skewed distributions.
FALLBACK_THRESHOLDS = {
    "duration_seconds": {"warning": 3600, "critical": 7200},  # 1h / 2h
    "tool_call_count": {"warning": 200, "critical": 500},
    "cached_output_tokens": {"warning": 200000, "critical": 500000},  # cache write hotspot
}

MIN_ROWS = 20


def percentile(values: list[float], pct: float) -> Optional[float]:
    """Compute the given percentile of a list of numbers.

    Returns None if the list is empty.
    """
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (pct / 100.0) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_vals[-1]
    d = k - f
    return sorted_vals[f] + d * (sorted_vals[c] - sorted_vals[f])


def compute_percentiles(
    values: list[float],
) -> dict[str, Optional[float]]:
    """Compute P90 and P95 for a list of values.

    Returns {"p90": ..., "p95": ..., "count": n}.
    """
    return {
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "count": len(values),
    }


def get_threshold(
    metric: str,
    values: list[float],
    severity: str = "warning",
) -> Optional[float]:
    """Get threshold for a metric, using percentile if enough data, else fallback.

    Args:
        metric: Key name (e.g., "duration_seconds").
        values: List of observed values.
        severity: "warning" or "critical".

    Returns:
        Threshold value, or None if metric not recognized.
    """
    fb = FALLBACK_THRESHOLDS.get(metric, {})
    threshold = fb.get(severity)
    if threshold is not None:
        return float(threshold)

    # For ratio-based metrics
    ratio_key = f"{severity}_ratio"
    if ratio_key in fb:
        return fb[ratio_key]

    return None


def compute_session_thresholds(
    sessions_data: list[dict],
) -> dict[str, dict]:
    """Compute anomaly thresholds for all session-level metrics.

    Args:
        sessions_data: List of dicts with session fields.

    Returns:
        Dict of {metric: {"warning": float, "critical": float, "p90": float, "p95": float, "n": int}}.
    """
    result = {}
    metrics_map = {
        "duration_seconds": "duration_seconds",
        "tool_call_count": "tool_call_count",
        "cached_output_tokens": "cached_output_tokens",
    }

    for metric_key, db_key in metrics_map.items():
        values = []
        for s in sessions_data:
            v = s.get(db_key, 0)
            if v is not None and v > 0:
                values.append(float(v))

        pcts = compute_percentiles(values)
        fb = FALLBACK_THRESHOLDS.get(metric_key, {})

        if pcts["count"] >= MIN_ROWS and pcts["p95"] is not None:
            warn = pcts["p95"]
            crit = pcts["p95"] * 1.5 if pcts["p95"] else fb.get("critical", warn * 1.5)
        else:
            warn = fb.get("warning", 0)
            crit = fb.get("critical", warn * 2)

        result[metric_key] = {
            "warning": warn,
            "critical": crit,
            "p90": pcts["p90"],
            "p95": pcts["p95"],
            "n": pcts["count"],
        }

    return result
