"""Payload lookup builder and truncation.

Extracted from routes.py. Builds the payload_id → payload_entry lookup
dict used by the session detail view model and the /api/.../payload endpoint.
"""

from __future__ import annotations

from session_browser.web.template_env import _format_bytes, _shorten_path
from session_browser.web.session_detail.render_helpers import _build_tool_command_summary


def _truncate_payload(text: str, limit: int) -> str:
    """Truncate payload text if it exceeds the byte limit."""
    if not text:
        return ""
    if limit <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) > limit:
        return encoded[:limit].decode("utf-8", "ignore")
    return text


def _build_payload_lookup(
    rounds: list,
    tool_calls: list,
    subagent_runs: list,
    truncate: bool = True,
) -> dict:
    """Build a payload lookup dict from parsed session data.

    Returns dict: {payload_id: {payload_id, kind, title, status, size, text}}

    When truncate=True, applies the same truncation limits as _build_v11_view_model:
      - subagent request/response: 5000 bytes
      - user message: 5000 bytes
      - tool result: 5000 bytes
      - LLM context/output: 10000 bytes
    When truncate=False, returns the full, untruncated text.
    """
    payload_map = {}

    def _assistant_text_from_call(ix) -> str:
        parts = []
        for block in getattr(ix, "content_blocks", []) or []:
            block_type = block.get("type", "")
            if block_type == "output_text":
                block_type = "text"
            if block_type not in ("text", "thinking"):
                continue
            text = block.get("content") or block.get("text") or block.get("thinking") or ""
            if str(text).strip():
                parts.append(str(text).strip())
        if parts:
            return "\n\n".join(parts)
        return getattr(ix, "response_full", "") or ""

    def _add(payload_id: str, kind: str, title: str, text: str = "",
             status: str = "available", byte_limit: int = 5000,
             tool_name: str = "", tool_command: str = "",
             tool_parameters: dict = None, tool_status: str = ""):
        final_text = _truncate_payload(text, byte_limit) if truncate else (text or "")
        byte_count = len(final_text.encode("utf-8")) if final_text else 0
        entry = {
            "payload_id": payload_id,
            "kind": kind,
            "title": title,
            "status": status if text else "empty",
            "size": _format_bytes(byte_count) if byte_count else "—",
            "text": final_text,
        }
        if tool_name:
            entry["tool_name"] = tool_name
        if tool_command:
            entry["tool_command"] = tool_command
        if tool_parameters:
            entry["tool_parameters"] = tool_parameters
        if tool_status:
            entry["tool_status"] = tool_status
        payload_map[payload_id] = entry

    # -- Subagent payloads --
    for run in subagent_runs:
        sa_id = run["summary"]["agent_id"]
        sa_messages = run.get("messages", [])
        for m_idx, m in enumerate(sa_messages):
            if m.role == "assistant":
                call_ref = m.llm_call_id or f"sub-{sa_id}-{m_idx + 1}"
                if m.request_full:
                    _add(
                        payload_id=f"sub-{sa_id}-{m_idx + 1}-ctx",
                        kind="subagent.request",
                        title=f"Subagent · Request ({call_ref})",
                        text=m.request_full,
                        byte_limit=5000,
                    )
                if m.content:
                    _add(
                        payload_id=f"sub-{sa_id}-{m_idx + 1}-rsp",
                        kind="subagent.response",
                        title=f"Subagent · Response ({call_ref})",
                        text=m.content,
                        byte_limit=5000,
                    )

    # -- Round-level payloads (user messages, tool results, LLM calls) --
    global_llm_call_num = 0
    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1

        # User message
        if r.user_msg.content:
            _add(
                payload_id=f"msg-R{rid}-user",
                kind="message.user",
                title=f"R{rid} · User request",
                text=r.user_msg.content,
                byte_limit=5000,
            )

        # Interaction-level payloads
        for ix in r.interactions:
            global_llm_call_num += 1
            iix = global_llm_call_num

            # Subagent interactions — payloads already handled above
            if ix.scope == "subagent" and ix.subagent_id:
                continue

            # Tool batch payloads
            if hasattr(ix, 'tool_calls') and ix.tool_calls:
                for tc in ix.tool_calls:
                    if tc.subagent_id or not tc.result:
                        continue
                    tc_global_idx = -1
                    for gi, gtc in enumerate(r.tool_calls):
                        if gtc is tc:
                            tc_global_idx = gi + 1
                            break
                    if tc_global_idx == -1:
                        tc_global_idx = len([t for t in ix.tool_calls if not t.subagent_id])
                    _add(
                        payload_id=f"tool-R{rid}-T{tc_global_idx}",
                        kind="tool.result",
                        title=f"R{rid} · {tc.name} · Result",
                        text=tc.result,
                        byte_limit=5000,
                        tool_name=tc.name,
                        tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                        tool_parameters=tc.parameters,
                        tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                    )

            # LLM context and output payloads
            if ix.request_full:
                _add(
                    payload_id=f"llm-R{rid}-IX{iix}-context",
                    kind="llm.context",
                    title=f"R{rid} · LLM Call #{iix} · Context",
                    text=ix.request_full,
                    byte_limit=10000,
                )
            if ix.response_full:
                _add(
                    payload_id=f"llm-R{rid}-IX{iix}-output",
                    kind="llm.output",
                    title=f"R{rid} · LLM Call #{iix} · Output",
                    text=ix.response_full,
                    byte_limit=10000,
                )
            assistant_text = _assistant_text_from_call(ix)
            if assistant_text:
                _add(
                    payload_id=f"llm-R{rid}-IX{iix}-assistant-text",
                    kind="llm.output",
                    title=f"R{rid} · LLM Call #{iix} · Assistant Text",
                    text=assistant_text,
                    byte_limit=10000,
                )

        # Standalone tool calls (rounds with no interactions but tool_calls present)
        if not r.interactions and r.tool_calls:
            for tc_idx, tc in enumerate(r.tool_calls):
                if tc.subagent_id or not tc.result:
                    continue
                _add(
                    payload_id=f"tool-R{rid}-T{tc_idx + 1}",
                    kind="tool.result",
                    title=f"R{rid} · {tc.name} · Result",
                    text=tc.result,
                    byte_limit=5000,
                    tool_name=tc.name,
                    tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                    tool_parameters=tc.parameters,
                    tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                )

    return payload_map
