"""Compute percentile thresholds for session-browser anomaly detection.

Provides P90/P95 computation with fallback thresholds for small datasets.
"""

from __future__ import annotations

# Fallback thresholds used when data is insufficient or skewed.
FALLBACK_THRESHOLDS = {
    "duration_seconds": {"warning": 3600, "critical": 7200},  # 1h / 2h
    "tool_call_count": {"warning": 200, "critical": 500},
    "cache_write_tokens": {"warning": 200000, "critical": 500000},
}

MIN_ROWS = 20


def percentile(values: list[float], pct: float) -> float | None:
    """Compute one percentile from numeric values.

    Anomaly threshold builders call this helper after filtering the metric values.
    The interpolation formula is unchanged and returns no threshold for empty input.

    Args:
        values: Numeric observations for one metric.
        pct: Percentile to compute, expressed from 0 to 100.

    Returns:
        Interpolated percentile value, or None when values is empty.
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
) -> dict[str, float | None]:
    """Compute P90, P95, and sample count for one metric series.

    Anomaly threshold code uses the result to decide whether enough data exists for
    percentile-based thresholds.

    Args:
        values: Numeric observations for one metric.

    Returns:
        Dictionary containing p90, p95, and count entries.
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
) -> float | None:
    """Return the configured fallback threshold for a metric and severity.

    Callers use this helper when they need the static anomaly threshold table rather
    than session-derived percentiles.

    Args:
        metric: Metric key such as duration_seconds or tool_call_count.
        values: Observed values kept for API compatibility; not used by fallback lookup.
        severity: Threshold severity name, normally warning or critical.

    Returns:
        Fallback threshold as a float, or None when the metric/severity is unknown.
    """
    fb = FALLBACK_THRESHOLDS.get(metric, {})
    threshold = fb.get(severity)
    if threshold is not None:
        return float(threshold)

    # Ratio-based metrics may use severity-specific keys in the fallback table.
    ratio_key = f"{severity}_ratio"
    if ratio_key in fb:
        return fb[ratio_key]

    return None


def compute_session_thresholds(
    sessions_data: list[dict],
) -> dict[str, dict]:
    """Compute warning and critical thresholds for session anomaly metrics.

    The anomaly detector calls this function with current session rows. It uses P95
    when enough positive observations exist and otherwise falls back to fixed
    thresholds.

    Args:
        sessions_data: Session dictionaries containing metric fields from the index.

    Returns:
        Mapping from metric name to warning, critical, p90, p95, and n values.
    """
    result = {}
    metrics_map = {
        "duration_seconds": "duration_seconds",
        "tool_call_count": "tool_call_count",
        "cache_write_tokens": "cache_write_tokens",
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
