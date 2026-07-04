#!/usr/bin/env python3
"""提供 write session 检查 脚本能力。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks import paths as runtime_paths  # noqa: E402
from scripts.quality import changed_files as changed_file_utils  # noqa: E402


# 解析命令行参数并运行脚本入口。
def main() -> None:
    """说明：
        token到 stdout. JSON 解析 失败项 in evidence are ignored so corrupt 行 does。
    """
    # 尝试从 stdin 读取 session ID (Claude hook 传入的 JSON)。
    session_id, agent_id = _read_identity_from_stdin()

    if not session_id:
        print('unknown')
        return

    identity = runtime_paths.identity_from_values(session_id=session_id, agent_id=agent_id or '')
    changed_paths = [
        path / 'changed-files.jsonl'
        for path in runtime_paths.session_log_dirs(
            REPO_ROOT,
            identity,
            include_agents=not identity.is_agent,
        )
    ]
    files = changed_file_utils.read_recorded_changed_files_from_paths(
        changed_paths,
        session_id,
        agent_id=agent_id,
    )
    if not files:
        print('no_changes')
        return
    print('has_changes')


# 读取session id stdin。
def _read_session_id_from_stdin() -> str | None:
    """返回：
        从 stdin 读取的 session id 字符串。
    """
    try:
        text = sys.stdin.read()
        if not text or not text.strip():
            return None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        sid = data.get('session_id') or data.get('sessionId') or ''
        return sid if sid else None
    except Exception:
        return None


# 读取identity stdin。
def _read_identity_from_stdin() -> tuple[str | None, str | None]:
    """返回：
        结果 tuple。
    """
    try:
        text = sys.stdin.read()
        if not text or not text.strip():
            return None, None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None, None
        sid = data.get('session_id') or data.get('sessionId') or ''
        aid = data.get('agent_id') or data.get('agentId') or ''
        return (sid if sid else None), (aid if aid else None)
    except Exception:
        return None, None


if __name__ == '__main__':
    main()
