"""Centralized tag registry for session diagnostics.

Two distinct groups:
- SESSION_ANOMALY_DEFINITIONS: session-level "needs attention" tags
- ROUND_SIGNAL_DEFINITIONS: round-level "worth investigating" tags

Templates and filters must derive their candidate values from these definitions,
not hard-code them.
"""

from __future__ import annotations

# ─── Session-level anomaly tags ─────────────────────────────────────────
# Used by: /dashboard Needs Attention, /sessions anomaly filter,
# session detail anomaly banner, glossary anomaly docs.

SESSION_ANOMALY_DEFINITIONS: dict[str, dict] = {
    "long_duration": {
        "key": "long_duration",
        "label": "Long Duration",
        "filter_label": "Long Duration",
        "filter_value": "long_duration",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": 3600,    # >= 1h model execution time
            "critical": 7200,   # >= 2h model execution time
        },
        "description": "Combined active time (LLM response intervals + tool execution with parallel overlap merged) exceeds thresholds. Warning at >= 1h, critical at >= 2h.",
    },
    "failed_run": {
        "key": "failed_run",
        "label": "Failed Tools",
        "filter_label": "Failed Tools",
        "filter_value": "failed",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": {"min_ratio": 0.15},
            "critical": {"min_ratio": 0.25},
        },
        "description": "Session has a high ratio of failed tool calls. "
                       "Warning at >= 15% failure ratio; critical at >= 25%.",
    },
    "cache_write_spike": {
        "key": "cache_write_spike",
        "label": "Cache Creation",
        "filter_label": "Cache Write",
        "filter_value": "cache_write",
        "severity_levels": ("info", "warning"),
        "thresholds": {
            "warning": 200_000,
            "critical": 500_000,  # kept for backward compat, but severity caps at warning
        },
        "description": "High cache creation tokens (cache_creation_input_tokens) indicate that this session generated "
                       "a large amount of context being written to the prompt cache for future rounds. "
                       "This is expected for multi-turn sessions with growing context — info/warning level only, "
                       "not a problem indicator like failures.",
    },
}

# ─── Round-level signal tags ────────────────────────────────────────────
# Used by: session detail Timeline SIGNALS column.

ROUND_SIGNAL_DEFINITIONS: dict[str, dict] = {
    "failed-tool": {
        "key": "failed-tool",
        "label": "failed tool",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": {"min_count": 1},
            "critical": {"min_count": 3},
        },
        "description": "Single round has failed tool calls. Warning at 1-2 failures; critical at >= 3.",
    },
    "llm-error": {
        "key": "llm-error",
        "label": "llm error",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": {"min_count": 1},
            "critical": {"min_count": 3},
        },
        "description": "Single round has LLM errors. Warning at 1-2; critical at >= 3.",
    },
    "long-tool": {
        "key": "long-tool",
        "label": "long tool",
        "severity_levels": ("warning",),
        "thresholds": {
            "warning": {"duration_ms": 300_000},  # >= 5 min
        },
        "description": "A single tool call in the round took >= 5 minutes.",
    },
    "tool-burst": {
        "key": "tool-burst",
        "label": "tool burst",
        "severity_levels": ("warning",),
        "thresholds": {
            "warning": {"min_count": 20},
        },
        "description": "Round has >= 20 tool calls (excluding tight loops where top 3 tools are >= 90% of calls).",
    },
    "high-write": {
        "key": "high-write",
        "label": "high write",
        "severity_levels": ("warning",),
        "thresholds": {
            "warning": {"cache_write": 300_000},
        },
        "description": "Round has cache write >= 300K tokens.",
    },
    "large-input": {
        "key": "large-input",
        "label": "large input",
        "severity_levels": ("warning",),
        "thresholds": {
            "warning": {"min_tokens": 200_000, "min_ratio": 0.50},
        },
        "description": "Round input >= 200K tokens AND >= 50% of session total input.",
    },
}

# ─── Helpers ────────────────────────────────────────────────────────────


def get_session_anomaly_filter_options() -> list[dict]:
    """Return filter dropdown options for session anomaly filters."""
    options = []
    for defn in SESSION_ANOMALY_DEFINITIONS.values():
        options.append({
            "value": defn["filter_value"],
            "label": defn["filter_label"],
        })
    return options


def get_session_anomaly_keys() -> set[str]:
    return set(SESSION_ANOMALY_DEFINITIONS.keys())


def get_round_signal_keys() -> set[str]:
    return set(ROUND_SIGNAL_DEFINITIONS.keys())
