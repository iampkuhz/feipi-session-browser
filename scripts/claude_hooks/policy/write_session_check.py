#!/usr/bin/env python3
"""判断当前 session 是否有 Write/Edit 文件修改记录。

由 stop.sh 调用，从 stdin 读取 Claude hook 上下文，提取 sessionId，
再查询 changed-files.jsonl 中是否有该 session 的写操作记录。

stdout 输出:
  no_changes  — 当前 session 无文件修改（只读会话）
  has_changes — 当前 session 有文件修改
  unknown     — 无法获取 session ID（保守处理，视为有变更）
"""
import json
import os
import sys
from pathlib import Path


def main() -> None:
    log_dir = os.environ.get("FEIPI_AGENT_LOG_DIR", "tmp/agent_log")
    changed_file = Path(log_dir) / "changed-files.jsonl"

    # 尝试从 stdin 读取 session ID（Claude hook 传入的 JSON）。
    session_id = _read_session_id_from_stdin()

    if not session_id:
        print("unknown")
        return

    if not changed_file.exists() or changed_file.stat().st_size == 0:
        print("no_changes")
        return

    for line in changed_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if record.get("sessionId") == session_id:
                print("has_changes")
                return
        except json.JSONDecodeError:
            continue

    print("no_changes")


def _read_session_id_from_stdin() -> str | None:
    """从 stdin JSON 中提取 sessionId。"""
    try:
        text = sys.stdin.read()
        if not text or not text.strip():
            return None
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        sid = data.get("session_id") or data.get("sessionId") or ""
        return sid if sid else None
    except Exception:
        return None


if __name__ == "__main__":
    main()
