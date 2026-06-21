"""Detect session-level anomalies for the index and web presentation flows.

The index and dashboard layers pass enriched session dictionaries into this
module. It returns structured anomaly records with stable type, severity, label,
and reason fields for filters, badges, and detail banners.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from session_browser.domain.enums import DomainStrEnum
from session_browser.domain.serializers import session_summary_to_dict
from session_browser.domain.session_models import SessionSummary
from session_browser.index.percentiles import FALLBACK_THRESHOLDS


class AnomalyType(DomainStrEnum):
    """Finite anomaly kinds emitted by the session anomaly detector.

    The dashboard and session-detail views compare these values against filter
    keys. Values are stable string contracts and must continue to match the
    diagnostics registry and templates.

    Attributes:
        LONG_DURATION: Active execution time exceeded the configured threshold.
        CACHE_WRITE_SPIKE: Cache creation tokens exceeded the configured threshold.
        FAILED_RUN: Failed tool-call ratio exceeded the configured threshold.
        PAYLOAD_VISIBILITY_MISMATCH: Payload visibility mismatch detected by the
            session-detail route.
    """

    LONG_DURATION = "long_duration"
    CACHE_WRITE_SPIKE = "cache_write_spike"
    FAILED_RUN = "failed_run"
    PAYLOAD_VISIBILITY_MISMATCH = "payload_visibility_mismatch"


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
FAILED_TOOL_CRITICAL_RATIO = 0.25
FAILED_TOOL_WARNING_RATIO = 0.15
SECONDS_PER_HOUR = 3600


@dataclass
class Anomaly:
    """Display-ready anomaly detected for one indexed session.

    The anomaly detector creates this value object after evaluating an enriched
    session row. Templates consume the fields directly, so severity and type must
    stay aligned with the constants in this module.

    Attributes:
        type: Stable anomaly key used by filters and templates.
        severity: One of ``critical``, ``warning``, or ``info``.
        label: Short human-readable label shown in badges.
        reason: Human-readable explanation shown in dashboard and detail views.
    """

    type: str
    severity: str
    label: str
    reason: str

    @property
    def badge_class(self) -> str:
        """Return the CSS badge class for this anomaly severity.

        Templates call this property while rendering anomaly badges. It maps the
        stored severity to the existing CSS class names and falls back to the
        informational badge for unknown severities.

        Returns:
            CSS class name for the rendered anomaly badge.
        """
        if self.severity == SEVERITY_CRITICAL:
            return "badge-anomaly-critical"
        if self.severity == SEVERITY_WARNING:
            return "badge-anomaly-warning"
        return "badge-anomaly-info"


@dataclass
class SessionAnomalies:
    """Anomaly collection for one indexed session.

    The anomaly scan builds one instance per session. The object keeps the
    original ``session_key`` and exposes derived display properties without
    mutating the underlying anomaly list.

    Attributes:
        session_key: Stable key for the indexed session row.
        anomalies: Ordered anomaly values detected for the session.
    """

    session_key: str
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def max_severity(self) -> str:
        """Return the highest severity present in this session.

        Dashboard sorting and filters call this property after anomaly detection.
        Critical wins over warning, and a session without anomalies reports the
        informational level to preserve existing display semantics.

        Returns:
            Highest severity string for this session's anomaly list.
        """
        if any(a.severity == SEVERITY_CRITICAL for a in self.anomalies):
            return SEVERITY_CRITICAL
        if any(a.severity == SEVERITY_WARNING for a in self.anomalies):
            return SEVERITY_WARNING
        return SEVERITY_INFO

    @property
    def main_reason(self) -> str:
        """Return the reason for the highest-severity anomaly.

        Dashboard cards call this property to show one summary sentence. Empty
        anomaly lists return an empty string, and tied severities preserve the
        existing sort-based first-item selection.

        Returns:
            Reason text for the highest-priority anomaly, or an empty string.
        """
        if not self.anomalies:
            return ""
        ordered = sorted(
            self.anomalies,
            key=lambda a: (
                0 if a.severity == SEVERITY_CRITICAL else 1 if a.severity == SEVERITY_WARNING else 2
            ),
        )
        return ordered[0].reason

    @property
    def display_count(self) -> int:
        """Return the number of anomalies displayed for this session.

        Dashboard templates call this property while rendering needs-attention
        cards. It mirrors the current anomaly list length without filtering.

        Returns:
            Count of anomaly records attached to the session.
        """
        return len(self.anomalies)


def safe_divide(a: float | None, b: float | None, default: float | None = None) -> float | None:
    """Divide two optional numbers without raising on missing or zero divisors.

    The anomaly detector uses this helper for ratio thresholds where malformed
    or missing counters should produce the caller-provided fallback instead of a
    runtime error.

    Args:
        a: Numerator value from a session counter.
        b: Denominator value from a session counter.
        default: Value returned when either operand cannot produce a ratio.

    Returns:
        ``a / b`` when both operands are usable, otherwise ``default``.
    """
    if b is None or b == 0:
        return default
    if a is None:
        return default
    return a / b


def detect_session_anomalies(
    session: dict,
    thresholds: dict | None = None,
) -> SessionAnomalies:
    """Detect all supported anomalies for one indexed session dictionary.

    Dashboard and list presenters call this after session rows have been enriched
    with counters. The optional threshold argument is accepted for compatibility;
    this implementation continues to use fallback thresholds for stable behavior.

    Args:
        session: Enriched session row or serialized ``SessionSummary`` fields.
        thresholds: Reserved precomputed threshold map; currently ignored.

    Returns:
        ``SessionAnomalies`` containing all detected anomaly records for the row.
    """
    _ = thresholds
    anomalies: list[Anomaly] = []
    session_key = session.get("session_key", "")

    tools = session.get("tool_call_count", 0) or 0
    failed = session.get("failed_tool_count", 0) or 0
    cache_write = session.get("cache_write_tokens", 0) or 0

    # Failed-run detection is ratio based so sessions with many successful tools
    # are not flagged for an occasional tool failure.
    if failed > 0 and tools > 0:
        fail_ratio = safe_divide(failed, tools, 0)
        if fail_ratio >= FAILED_TOOL_CRITICAL_RATIO:
            anomalies.append(
                Anomaly(
                    type=AnomalyType.FAILED_RUN,
                    severity=SEVERITY_CRITICAL,
                    label="Failed Tools",
                    reason=f"{failed} failed tool call(s) ({fail_ratio * 100:.0f}%)",
                )
            )
        elif fail_ratio >= FAILED_TOOL_WARNING_RATIO:
            anomalies.append(
                Anomaly(
                    type=AnomalyType.FAILED_RUN,
                    severity=SEVERITY_WARNING,
                    label="Failed Tools",
                    reason=f"{failed} failed tool call(s) ({fail_ratio * 100:.0f}%)",
                )
            )

    # Active time combines model and tool execution while excluding idle wait.
    model_exec = session.get("model_execution_seconds", 0) or 0
    tool_exec = session.get("tool_execution_seconds", 0) or 0
    active_time = model_exec + tool_exec
    if active_time > 0:
        warn = FALLBACK_THRESHOLDS["duration_seconds"]["warning"]
        crit = FALLBACK_THRESHOLDS["duration_seconds"]["critical"]

        if active_time >= crit:
            hours = active_time / SECONDS_PER_HOUR
            anomalies.append(
                Anomaly(
                    type=AnomalyType.LONG_DURATION,
                    severity=SEVERITY_CRITICAL,
                    label="Long Duration",
                    reason=(
                        f"Active time {hours:.1f}h "
                        f"(model {model_exec / SECONDS_PER_HOUR:.1f}h + "
                        f"tool {tool_exec / SECONDS_PER_HOUR:.1f}h) exceeds "
                        f"critical threshold ({crit / SECONDS_PER_HOUR:.1f}h)"
                    ),
                )
            )
        elif active_time >= warn:
            hours = active_time / SECONDS_PER_HOUR
            anomalies.append(
                Anomaly(
                    type=AnomalyType.LONG_DURATION,
                    severity=SEVERITY_WARNING,
                    label="Long Duration",
                    reason=(
                        f"Active time {hours:.1f}h "
                        f"(model {model_exec / SECONDS_PER_HOUR:.1f}h + "
                        f"tool {tool_exec / SECONDS_PER_HOUR:.1f}h) exceeds "
                        f"warning threshold ({warn / SECONDS_PER_HOUR:.1f}h)"
                    ),
                )
            )

    # Cache creation is a visibility signal, not a failure indicator.
    warn = FALLBACK_THRESHOLDS["cache_write_tokens"]["warning"]
    crit = FALLBACK_THRESHOLDS["cache_write_tokens"]["critical"]

    if cache_write >= crit:
        anomalies.append(
            Anomaly(
                type=AnomalyType.CACHE_WRITE_SPIKE,
                severity=SEVERITY_WARNING,
                label="Cache Creation",
                reason=f"Cache creation {cache_write:,} tokens exceeds threshold ({crit:,})",
            )
        )
    elif cache_write >= warn:
        anomalies.append(
            Anomaly(
                type=AnomalyType.CACHE_WRITE_SPIKE,
                severity=SEVERITY_INFO,
                label="Cache Creation",
                reason=f"Cache creation {cache_write:,} tokens exceeds threshold ({warn:,})",
            )
        )

    # Payload visibility mismatch detection lives in the session route where LLM
    # call payloads are available; this module keeps only the stable type value.
    return SessionAnomalies(session_key=session_key, anomalies=anomalies)


def detect_all_anomalies(
    sessions_data: list[dict],
) -> dict[str, SessionAnomalies]:
    """Detect anomalies for every session row in a batch.

    The dashboard list flow calls this helper after loading session rows. It
    preserves the input iteration order in the returned mapping insertion order.

    Args:
        sessions_data: Session dictionaries keyed by ``session_key``.

    Returns:
        Mapping from session key to detected anomaly collection.
    """
    result = {}
    for session in sessions_data:
        key = session.get("session_key", "")
        result[key] = detect_session_anomalies(session)

    return result


def get_needs_attention(
    anomalies_map: dict[str, SessionAnomalies],
    sessions_lookup: dict[str, dict],
    limit: int = 8,
    filter_type: str = "all",
) -> list[dict]:
    """Build the sorted dashboard list of sessions needing attention.

    Dashboard routes call this after anomaly detection. It applies the requested
    anomaly filter, joins session display fields, and returns critical sessions
    before warnings while preserving existing count-based tie breaking.

    Args:
        anomalies_map: Detected anomaly collections keyed by session key.
        sessions_lookup: Session dictionaries keyed by session key.
        limit: Maximum number of display rows to return.
        filter_type: Filter key such as ``all``, ``critical``, ``long_duration``,
            ``cache_write``, or ``failed``.

    Returns:
        Sorted list of session dictionaries enriched with anomaly display fields.
    """
    items = []
    for key, session_anomalies in anomalies_map.items():
        if not session_anomalies.anomalies:
            continue

        if filter_type == "critical" and session_anomalies.max_severity != SEVERITY_CRITICAL:
            continue
        if filter_type == "long_duration" and not any(
            a.type == AnomalyType.LONG_DURATION for a in session_anomalies.anomalies
        ):
            continue
        if filter_type == "cache_write" and not any(
            a.type == AnomalyType.CACHE_WRITE_SPIKE for a in session_anomalies.anomalies
        ):
            continue
        if filter_type == "failed" and not any(
            a.type == AnomalyType.FAILED_RUN for a in session_anomalies.anomalies
        ):
            continue

        session = sessions_lookup.get(key, {})
        items.append(
            {
                "session_key": key,
                "session_id": session.get("session_id", ""),
                "agent": session.get("agent", ""),
                "title": session.get("title", "Untitled"),
                "project_name": session.get("project_name", ""),
                "project_key": session.get("project_key", ""),
                "model": session.get("model", ""),
                "ended_at": session.get("ended_at", ""),
                "max_severity": session_anomalies.max_severity,
                "main_reason": session_anomalies.main_reason,
                "anomaly_count": session_anomalies.display_count,
                "anomaly_types": [a.type for a in session_anomalies.anomalies],
                "anomaly_labels": [a.label for a in session_anomalies.anomalies],
                "anomaly_badge_classes": [a.badge_class for a in session_anomalies.anomalies],
            }
        )

    severity_order = {SEVERITY_CRITICAL: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
    items.sort(key=lambda x: (severity_order.get(x["max_severity"], 3), -x["anomaly_count"]))

    return items[:limit]


def enrich_sessions_with_anomalies(
    sessions: list,
    anomalies_map: dict[str, SessionAnomalies],
) -> list[dict]:
    """Append anomaly display fields to session summary objects or dictionaries.

    List presenters call this helper before rendering session tables. It keeps
    the original session data intact except for adding anomaly-related fields to
    the serialized output dictionaries.

    Args:
        sessions: ``SessionSummary`` objects or session dictionaries to enrich.
        anomalies_map: Detected anomaly collections keyed by session key.

    Returns:
        List of session dictionaries with ``anomalies``, ``max_severity``, and
        ``main_reason`` fields appended.
    """
    result = []
    for session in sessions:
        key = (
            session.session_key
            if hasattr(session, "session_key")
            else session.get("session_key", "")
        )
        session_anomalies = anomalies_map.get(key)
        data = (
            session_summary_to_dict(session)
            if isinstance(session, SessionSummary)
            else dict(session)
        )

        if session_anomalies and session_anomalies.anomalies:
            data["anomalies"] = [
                {
                    "type": anomaly.type,
                    "severity": anomaly.severity,
                    "label": anomaly.label,
                    "reason": anomaly.reason,
                    "badge_class": anomaly.badge_class,
                }
                for anomaly in session_anomalies.anomalies
            ]
            data["max_severity"] = session_anomalies.max_severity
            data["main_reason"] = session_anomalies.main_reason
        else:
            data["anomalies"] = []
            data["max_severity"] = None
            data["main_reason"] = None

        result.append(data)
    return result
