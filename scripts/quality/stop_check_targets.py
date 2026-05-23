#!/usr/bin/env python3
"""Stop hook: 检查所有 required quality targets 是否已有 PASS artifact。

不运行任何测试，只验证 artifact 是否存在且状态为 PASS。
根据当前 session 的文件修改，确定需要检查的 targets。

退出码:
    0 — 所有 required targets 已有 PASS artifact
    1 — 存在 missing/FAIL/stale artifact
"""
import json
import os
import sys
from pathlib import Path

from scripts.claude_hooks.classify import required_quality_targets

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_DIR = Path(os.environ.get("FEIPI_AGENT_LOG_DIR", "tmp/agent_logs/adhoc"))
CHANGED_FILES = LOG_DIR / "changed-files.jsonl"
QUALITY_DIR = LOG_DIR / "quality"
SESSION_ID_FILE = LOG_DIR / "session-id.txt"


def get_session_id() -> str | None:
    if SESSION_ID_FILE.exists():
        return SESSION_ID_FILE.read_text().strip() or None
    return None


def get_changed_files_for_session() -> list[str]:
    """获取当前 session 的变更文件列表。

    依据：按 sessionId 过滤 changed-files.jsonl（来自 post-write hook）。
    如果没有 session-id.txt，说明 SessionStart 未触发或无法提取 session ID，
    无法可靠确定本次改了什么，返回空列表（跳过质量 target 检查）。
    """
    session_id = get_session_id()
    if not session_id:
        return []

    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for line in CHANGED_FILES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if record.get("sessionId") == session_id:
                f = record.get("file") or record.get("file_path")
                if f:
                    files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


def check_target_artifact(target: str) -> tuple[bool, str]:
    """检查 target 是否有 PASS quality artifact。返回 (passed, message)。"""
    candidates = []
    if QUALITY_DIR.exists():
        for change_dir in sorted(QUALITY_DIR.iterdir()):
            if change_dir.is_dir():
                summary = change_dir / f"quality-gate-summary.{target}.json"
                if summary.exists():
                    candidates.append(summary)

    if not candidates:
        return False, f"缺少 {target} quality artifact（未在 tmp/quality/*/quality-gate-summary.{target}.json 找到记录）"

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        status = str(data.get("status", "")).upper()
        if status != "PASS":
            return False, f"{target} quality artifact 状态为 {status}（文件：{latest.relative_to(LOG_DIR)})"
        return True, f"{target} quality gate PASS（文件：{latest.relative_to(LOG_DIR)}）"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"{target} quality artifact 读取失败：{e}"


def main() -> int:
    changed_files = get_changed_files_for_session()
    if not changed_files:
        print("[stop_check_targets] 无文件变更记录，跳过 quality target 检查", file=sys.stderr)
        return 0

    targets = required_quality_targets(changed_files)
    if not targets:
        print("[stop_check_targets] 无文件需要 quality gate，跳过", file=sys.stderr)
        return 0

    blocked = False
    for target in sorted(targets):
        passed, msg = check_target_artifact(target)
        status_str = "PASS" if passed else "BLOCK"
        print(f"[stop_check_targets] [{status_str}] {target}: {msg}", file=sys.stderr)
        if not passed:
            blocked = True

    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
