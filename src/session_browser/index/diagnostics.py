"""Centralized tag registry，用于 session diagnostics.

Two distinct groups:
- SESSION_ANOMALY_DEFINITIONS: session-level "needs attention" tags
- ROUND_SIGNAL_DEFINITIONS: round-level "worth investigating" tags

Templates and filters must derive their candidate values from these definitions,
not hard-code them.

ParseDiagnostics bridges JSONL-level parse diagnostics (from jsonl_reader.JsonlDiagnostics)
to the domain layer, enabling the indexer and anomaly engine to see parse-time issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


# 说明：─── Parse-level severity & issues ────────────────────────────────────────


class ParseSeverity(Enum):
    """Parse-diagnostic severity (domain-level, decoupled，来源于 JSONL reader)."""
    INFO = auto()
    WARNING = auto()
    CRITICAL = auto()


class ParseIssue(Enum):
    """说明：Categories of parse-time issues that affect session quality."""
    # JSONL-level issues (mapped，来源于 jsonl_reader.ParseIssue)
    BAD_JSON = "BAD_JSON"
    NON_OBJECT_SKIPPED = "NON_OBJECT_SKIPPED"

    # 说明：File-level issues
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    EMPTY_FILE = "EMPTY_FILE"

    # 说明：Data-quality issues
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    TOKEN_ESTIMATED = "TOKEN_ESTIMATED"


@dataclass
class ParseIssueItem:
    """Single parse-level issue attached to 一个 session."""
    issue: ParseIssue
    severity: ParseSeverity
    message: str
    line_no: int = 0          # 阈值说明：0 = file-level; >0 = JSONL line number
    detail: str = ""          # 可选上下文（bad JSON 预览等）


@dataclass
class ParseDiagnostics:
    """Domain-level parse diagnostics，用于 一个 single session.

    Produced by converting jsonl_reader.JsonlDiagnostics via build_parse_diagnostics(),
    optionally enriched with adapter-specific issues (FILE_NOT_FOUND, TOKEN_ESTIMATED, etc.).
    """
    session_key: str = ""
    file_path: str = ""

    total_lines: int = 0
    events_parsed: int = 0
    events_skipped: int = 0

    issues: list[ParseIssueItem] = field(default_factory=list)

    # 说明：─── Computed properties ──────────────────────────────────────────

    @property
    def has_critical(self) -> bool:
        return any(i.severity == ParseSeverity.CRITICAL for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == ParseSeverity.WARNING for i in self.issues)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ParseSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ParseSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ParseSeverity.INFO)

    # 说明：─── Mutators ─────────────────────────────────────────────────────

    def add(self, item: ParseIssueItem) -> None:
        self.issues.append(item)

    # 说明：─── Serialization ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_key": self.session_key,
            "file_path": self.file_path,
            "total_lines": self.total_lines,
            "events_parsed": self.events_parsed,
            "events_skipped": self.events_skipped,
            "has_critical": self.has_critical,
            "has_warnings": self.has_warnings,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "issues": [
                {
                    "issue": item.issue.value if isinstance(item.issue, Enum) else item.issue,
                    "severity": item.severity.name if isinstance(item.severity, Enum) else item.severity,
                    "message": item.message,
                    "line_no": item.line_no,
                    "detail": item.detail,
                }
                for item in self.issues
            ],
        }


# 说明：─── Builder: JSONL reader → domain ParseDiagnostics ─────────────────────


def build_parse_diagnostics(
    session_key: str,
    file_path: str,
    jsonl_diag,                       # jsonl_reader.JsonlDiagnostics 对象
) -> ParseDiagnostics:
    """转换 一个 JsonlDiagnostics，来源于 该 JSONL reader，转换为 domain-level ParseDiagnostics.

    This is the primary bridge between the parsing layer and the domain layer.
    """
    diag = ParseDiagnostics(
        session_key=session_key,
        file_path=file_path,
        total_lines=jsonl_diag.total_lines,
        events_parsed=jsonl_diag.events_parsed,
        events_skipped=jsonl_diag.events_skipped,
    )

    for item in jsonl_diag.issues:
        # 映射 jsonl_reader ParseSeverity → domain ParseSeverity
        if item.severity.name == "ERROR":
            sev = ParseSeverity.CRITICAL
        elif item.severity.name == "WARNING":
            sev = ParseSeverity.WARNING
        else:
            sev = ParseSeverity.INFO

        diag.issues.append(ParseIssueItem(
            issue=ParseIssue(item.issue.value),
            severity=sev,
            message=item.detail,
            line_no=item.line_no,
            detail=item.preview,
        ))

    return diag


# 说明：─── Session-level anomaly tags ─────────────────────────────────────────
# 说明：Used by: /dashboard Needs Attention, /sessions anomaly filter,
# 说明：session detail anomaly banner, glossary anomaly docs.

SESSION_ANOMALY_DEFINITIONS: dict[str, dict] = {
    "long_duration": {
        "key": "long_duration",
        "label": "Long Duration",
        "filter_label": "Long Duration",
        "filter_value": "long_duration",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": 3600,    # 阈值说明：>= 1h model execution time
            "critical": 7200,   # 阈值说明：>= 2h model execution time
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
        },
        "description": "High cache creation tokens (cache_creation_input_tokens) indicate that this session generated "
                       "a large amount of context being written to the prompt cache for future rounds. "
                       "This is expected for multi-turn sessions with growing context — info/warning level only, "
                       "not a problem indicator like failures.",
    },
}

# 说明：─── Round-level signal tags ────────────────────────────────────────────
# 说明：Used by: session detail Timeline SIGNALS column.

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
            "warning": {"duration_ms": 300_000},  # 阈值说明：>= 5 min
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

# 说明：─── Helpers ────────────────────────────────────────────────────────────


def get_session_anomaly_filter_options() -> list[dict]:
    """返回 filter dropdown options，用于 session anomaly filters."""
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
