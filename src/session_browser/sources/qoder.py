"""Qoder 本地 session 数据解析器。

Qoder is a Claude Code-based IDE agent. Its data format closely mirrors
Claude Code's:
- ~/.qoder/projects/{url_encoded_path}/{sessionId}.jsonl: full conversation event stream
- No central history.jsonl — sessions are discovered by scanning projects/

Events share the same type/message/timestamp structure as Claude Code,
with additional fields: agentId, isMeta, userType, version.

This module is a re-export facade. Actual implementations live in
``session_browser.sources.qoder_parts.*``.
"""

from __future__ import annotations

from session_browser.sources.qoder_parts import *  # 说明：noqa: F401,F403
