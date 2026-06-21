#!/usr/bin/env python3
"""Stop hook: 检查所有 required quality targets 是否已有 PASS artifact.

不运行任何测试,只验证 artifact 是否存在且状态为 PASS.
根据当前 session 的文件修改,确定需要检查的 targets.

排除 "session-detail" target — 该 target 由 stop_quality_gate.py 单独处理.

退出码:
    0 — 所有 required targets 已有 PASS artifact
    1 — 存在 missing/FAIL/stale artifact
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks.classify import required_quality_targets  # noqa: E402

AGENT_LOG_DIR = REPO_ROOT / 'tmp' / 'agent_logs' / 'current'
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
# 质量 artifact 统一写入 tmp/quality/<change-id>/
QUALITY_DIR = REPO_ROOT / 'tmp' / 'quality'
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'

# session-detail 由 stop_quality_gate.py 单独检查,此处排除
EXCLUDED_TARGETS = {'session-detail'}


def get_session_id() -> str | None:
    """Read the current agent session id for stop-hook target checks.

    Returns:
        Computed result.
    """
    if SESSION_ID_FILE.exists():
        return SESSION_ID_FILE.read_text().strip() or None
    return None


def get_changed_files_for_session() -> list[str]:
    """获取当前 session 的变更文件列表.

    Returns:
        Computed result.
    """
    session_id = get_session_id()
    if not session_id:
        return []

    if not CHANGED_FILES.exists():
        return []

    files: list[str] = []
    for raw_line in CHANGED_FILES.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if record.get('sessionId') == session_id:
                f = record.get('file') or record.get('file_path')
                if f:
                    files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


def resolve_change_id() -> str:
    """从 tmp/active_change.json 解析 change-id.

    Returns:
        Computed result.
    """
    active_change = REPO_ROOT / 'tmp' / 'active_change.json'
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            cid = data.get('change_id', '')
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            pass
    return 'unknown'


def find_existing_summaries() -> list[Path]:
    """查找 QUALITY_DIR 下所有 quality-gate-summary.*.json 文件.

    Returns:
        Computed result.
    """
    summaries: list[Path] = []
    if QUALITY_DIR.exists():
        for change_dir in sorted(QUALITY_DIR.iterdir()):
            if change_dir.is_dir():
                for f in sorted(change_dir.iterdir()):
                    if f.name.startswith('quality-gate-summary.') and f.name.endswith('.json'):
                        summaries.append(f)
    return summaries


def check_target_artifact(target: str, change_id: str) -> tuple[bool, str]:
    """检查 target 是否有 PASS quality artifact.返回 (passed, message).

    Args:
        target: Input value for target.
        change_id: Input value for change_id.

    Returns:
        Computed result.
    """
    candidates = []
    if QUALITY_DIR.exists():
        for change_dir in sorted(QUALITY_DIR.iterdir()):
            if change_dir.is_dir():
                summary = change_dir / f'quality-gate-summary.{target}.json'
                if summary.exists():
                    candidates.append(summary)

    if not candidates:
        expected = f'{QUALITY_DIR}/<change-id>/quality-gate-summary.{target}.json'
        existing = find_existing_summaries()
        existing_rel = [str(p.relative_to(REPO_ROOT)) for p in existing] if existing else ['无']

        msg_parts = [
            f'缺少 {target} quality artifact',
            f'  expected: {expected}',
            f'  change-id: {change_id}',
            f'  agent-log-dir: {AGENT_LOG_DIR}',
            '  required targets: '
            f'{sorted(required_quality_targets(get_changed_files_for_session()))}',
            f'  actual found summaries: {", ".join(existing_rel)}',
        ]
        return False, '\n'.join(msg_parts)

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding='utf-8'))
        status = str(data.get('status', '')).upper()
        if status != 'PASS':
            return (
                False,
                f'{target} quality artifact 状态为 {status}(文件:{latest.relative_to(REPO_ROOT)})',
            )
        return True, f'{target} quality gate PASS(文件:{latest.relative_to(REPO_ROOT)})'
    except (json.JSONDecodeError, OSError) as e:
        return False, f'{target} quality artifact 读取失败:{e}'


def main() -> int:
    """Verify that required quality targets already have PASS artifacts.

    Returns:
        Computed result.
    """
    changed_files = get_changed_files_for_session()
    if not changed_files:
        print('[stop_check_targets] 无文件变更记录,跳过 quality target 检查', file=sys.stderr)
        return 0

    all_targets = required_quality_targets(changed_files)
    # 排除已由 stop_quality_gate.py 处理的 target
    targets = [t for t in all_targets if t not in EXCLUDED_TARGETS]

    if not targets:
        print(
            '[stop_check_targets] 无文件需要 quality gate'
            f'(排除 {", ".join(sorted(EXCLUDED_TARGETS))}),跳过',
            file=sys.stderr,
        )
        return 0

    change_id = resolve_change_id()
    results: list[tuple[str, bool, str]] = []
    for target in sorted(targets):
        passed, msg = check_target_artifact(target, change_id)
        results.append((target, passed, msg))

    # 输出简洁摘要
    fail_count = sum(1 for _, p, _ in results if not p)

    if fail_count == 0:
        print(f'[stop_check_targets] PASS — {len(targets)} target(s) 全部通过', file=sys.stderr)
        for target, _, _msg in results:
            print(f'  [PASS] {target}', file=sys.stderr)
        return 0

    # 有失败:输出摘要 + 精确 rerun 命令
    print(
        f'[stop_check_targets] BLOCK — {fail_count}/{len(targets)} target(s) 未通过',
        file=sys.stderr,
    )
    print(file=sys.stderr)
    for target, passed, msg in results:
        status_str = 'PASS' if passed else 'BLOCK'
        short_msg = msg.split('\n')[0] if '\n' in msg else msg
        print(f'  [{status_str}] {target}: {short_msg}', file=sys.stderr)

    print(file=sys.stderr)
    print('--- 精确 rerun 命令 ---', file=sys.stderr)
    for target, passed, _ in results:
        if not passed:
            print(
                '  python3 scripts/quality/run_quality_gate.py '
                f'--target {target} --change-id {change_id}',
                file=sys.stderr,
            )
    print(file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
