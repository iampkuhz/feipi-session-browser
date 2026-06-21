"""Define diagnostic registries and parse diagnostics for indexed sessions.

The indexer, anomaly engine, and templates use this module as the shared source
of truth for parse issues, session anomaly tags, and round-level signal tags.
Registry values are data contracts for filters and display labels, not runtime
business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from session_browser.sources.jsonl_reader import JsonlDiagnostics


class ParseSeverity(Enum):
    """Domain severity levels for parse diagnostics.

    Source adapters create JSONL-reader severities first, then
    ``build_parse_diagnostics`` maps them into this domain enum for index and
    display code.

    Attributes:
        INFO: Informational issue that does not indicate data loss.
        WARNING: Recoverable issue that may affect displayed session quality.
        CRITICAL: Parse failure that should be treated as a critical session
            issue.
    """

    INFO = auto()
    WARNING = auto()
    CRITICAL = auto()


class ParseIssue(Enum):
    """Domain issue categories that can affect indexed session quality.

    The parse diagnostics bridge and source adapters use these stable values to
    expose file-level, JSONL-level, and data-quality issues to the index layer.

    Attributes:
        BAD_JSON: A JSONL line could not be parsed as JSON.
        NON_OBJECT_SKIPPED: A JSONL line parsed but was not an object event.
        FILE_NOT_FOUND: A source file expected by discovery was missing.
        EMPTY_FILE: A source file had no parseable events.
        MISSING_TIMESTAMP: An event or session lacked expected timestamp data.
        TOKEN_ESTIMATED: Token values were estimated instead of read directly.
    """

    BAD_JSON = "BAD_JSON"
    NON_OBJECT_SKIPPED = "NON_OBJECT_SKIPPED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    EMPTY_FILE = "EMPTY_FILE"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    TOKEN_ESTIMATED = "TOKEN_ESTIMATED"


@dataclass
class ParseIssueItem:
    """Single parse-level issue attached to one session.

    The JSONL diagnostics bridge creates these items while converting raw reader
    diagnostics. Line number ``0`` represents a file-level issue; positive values
    identify a JSONL line.

    Attributes:
        issue: Stable domain issue category.
        severity: Domain severity assigned to the issue.
        message: Human-readable issue message.
        line_no: Source line number, or ``0`` for file-level issues.
        detail: Optional context such as a bad JSON preview.
    """

    issue: ParseIssue
    severity: ParseSeverity
    message: str
    line_no: int = 0
    detail: str = ""


@dataclass
class ParseDiagnostics:
    """Domain-level parse diagnostics for one indexed session.

    Source adapters build this object from ``JsonlDiagnostics`` and may append
    adapter-specific issues before index writers or presenters inspect it. Count
    properties derive from the mutable ``issues`` list.

    Attributes:
        session_key: Stable key for the affected session.
        file_path: Source file path for the parsed session.
        total_lines: Number of lines seen by the source reader.
        events_parsed: Number of event objects accepted by the reader.
        events_skipped: Number of source entries skipped during parsing.
        issues: Parse issue items collected for the session.
    """

    session_key: str = ""
    file_path: str = ""
    total_lines: int = 0
    events_parsed: int = 0
    events_skipped: int = 0
    issues: list[ParseIssueItem] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        """Return whether any critical parse issue is present.

        Presenters call this property when deciding whether a session needs a
        critical parse warning.

        Returns:
            ``True`` when at least one issue has critical severity.
        """
        return any(i.severity == ParseSeverity.CRITICAL for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Return whether any warning parse issue is present.

        Presenters call this property when deciding whether to show recoverable
        parse warnings for the session.

        Returns:
            ``True`` when at least one issue has warning severity.
        """
        return any(i.severity == ParseSeverity.WARNING for i in self.issues)

    @property
    def critical_count(self) -> int:
        """Return the number of critical parse issues.

        Dashboard summaries call this property to display severity counts derived
        from the current issue list.

        Returns:
            Count of issues with critical severity.
        """
        return sum(1 for i in self.issues if i.severity == ParseSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        """Return the number of warning parse issues.

        Dashboard summaries call this property to display severity counts derived
        from the current issue list.

        Returns:
            Count of issues with warning severity.
        """
        return sum(1 for i in self.issues if i.severity == ParseSeverity.WARNING)

    @property
    def info_count(self) -> int:
        """Return the number of informational parse issues.

        Dashboard summaries call this property to display severity counts derived
        from the current issue list.

        Returns:
            Count of issues with informational severity.
        """
        return sum(1 for i in self.issues if i.severity == ParseSeverity.INFO)

    def add(self, item: ParseIssueItem) -> None:
        """Append one parse issue to this diagnostics object.

        Source adapters call this mutator when adding adapter-specific issues
        after the JSONL-reader bridge has populated base diagnostics.

        Args:
            item: Parse issue item to append to ``issues``.
        """
        self.issues.append(item)

    def to_dict(self) -> dict:
        """Serialize parse diagnostics for templates and API-style consumers.

        Presenters call this before rendering parse details. Enum fields are
        converted to stable string values while counts are computed from the
        current issue list.

        Returns:
            Dictionary containing session identity, line and event counts,
            severity booleans, severity counts, and serialized issue entries.
        """
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
                    "severity": (
                        item.severity.name if isinstance(item.severity, Enum) else item.severity
                    ),
                    "message": item.message,
                    "line_no": item.line_no,
                    "detail": item.detail,
                }
                for item in self.issues
            ],
        }


def build_parse_diagnostics(
    session_key: str,
    file_path: str,
    jsonl_diag: JsonlDiagnostics,
) -> ParseDiagnostics:
    """Convert JSONL-reader diagnostics into domain parse diagnostics.

    Source adapters call this bridge after reading a JSONL session file. It keeps
    reader counts unchanged, maps reader severities into domain severities, and
    copies issue detail and preview text for display.

    Args:
        session_key: Stable key of the parsed session.
        file_path: Source path used by the reader.
        jsonl_diag: Diagnostics object returned by the JSONL reader.

    Returns:
        Domain parse diagnostics populated with counts and mapped issue items.
    """
    diag = ParseDiagnostics(
        session_key=session_key,
        file_path=file_path,
        total_lines=jsonl_diag.total_lines,
        events_parsed=jsonl_diag.events_parsed,
        events_skipped=jsonl_diag.events_skipped,
    )

    for item in jsonl_diag.issues:
        if item.severity.name == "ERROR":
            sev = ParseSeverity.CRITICAL
        elif item.severity.name == "WARNING":
            sev = ParseSeverity.WARNING
        else:
            sev = ParseSeverity.INFO

        diag.issues.append(
            ParseIssueItem(
                issue=ParseIssue(item.issue.value),
                severity=sev,
                message=item.detail,
                line_no=item.line_no,
                detail=item.preview,
            )
        )

    return diag


SESSION_ANOMALY_DEFINITIONS: dict[str, dict] = {
    "long_duration": {
        "key": "long_duration",
        "label": "Long Duration",
        "filter_label": "Long Duration",
        "filter_value": "long_duration",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": 3600,
            "critical": 7200,
        },
        "description": (
            "Combined active time (LLM response intervals + tool execution with parallel "
            "overlap merged) exceeds thresholds. Warning at >= 1h, critical at >= 2h."
        ),
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
        "description": (
            "Session has a high ratio of failed tool calls. Warning at >= 15% failure "
            "ratio; critical at >= 25%."
        ),
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
        "description": (
            "High cache creation tokens (cache_creation_input_tokens) indicate that this "
            "session generated a large amount of context being written to the prompt "
            "cache for future rounds. This is expected for multi-turn sessions with "
            "growing context - info/warning level only, not a problem indicator like "
            "failures."
        ),
    },
}

ROUND_SIGNAL_DEFINITIONS: dict[str, dict] = {
    "failed-tool": {
        "key": "failed-tool",
        "label": "failed tool",
        "severity_levels": ("warning", "critical"),
        "thresholds": {
            "warning": {"min_count": 1},
            "critical": {"min_count": 3},
        },
        "description": (
            "Single round has failed tool calls. Warning at 1-2 failures; critical at >= 3."
        ),
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
            "warning": {"duration_ms": 300_000},
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
        "description": (
            "Round has >= 20 tool calls (excluding tight loops where top 3 tools are "
            ">= 90% of calls)."
        ),
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


def get_session_anomaly_filter_options() -> list[dict]:
    """Return dropdown options for session anomaly filters.

    Session list routes call this helper to derive filter values from the shared
    anomaly registry instead of hard-coding template options.

    Returns:
        List of option dictionaries with ``value`` and ``label`` keys.
    """
    options = []
    for defn in SESSION_ANOMALY_DEFINITIONS.values():
        options.append(
            {
                "value": defn["filter_value"],
                "label": defn["filter_label"],
            }
        )
    return options


def get_session_anomaly_keys() -> set[str]:
    """Return all registered session-level anomaly keys.

    Filters and validation helpers call this function when they need the stable
    set of supported session anomaly identifiers.

    Returns:
        Set of keys from ``SESSION_ANOMALY_DEFINITIONS``.
    """
    return set(SESSION_ANOMALY_DEFINITIONS.keys())


def get_round_signal_keys() -> set[str]:
    """Return all registered round-level signal keys.

    Session-detail presenters call this function when validating or documenting
    round signal tags.

    Returns:
        Set of keys from ``ROUND_SIGNAL_DEFINITIONS``.
    """
    return set(ROUND_SIGNAL_DEFINITIONS.keys())
