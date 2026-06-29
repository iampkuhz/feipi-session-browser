#!/usr/bin/env python3
"""Stop hook: 检查所有 required quality targets 是否已有 PASS artifact.

不运行任何测试,只验证 artifact 是否存在且状态为 PASS.
根据当前 session 的文件修改,确定需要检查的 targets.

排除 "session-detail" target — 该 target 由 shared stop runner 显式执行.

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

from scripts.claude_hooks.classify import effective_targets, required_quality_targets  # noqa: E402
from scripts.quality import changed_files as changed_file_utils  # noqa: E402

AGENT_LOG_DIR = REPO_ROOT / 'tmp' / 'agent_logs' / 'current'
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
# 质量 artifact 统一写入 tmp/quality/<change-id>/
QUALITY_DIR = REPO_ROOT / 'tmp' / 'quality'
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'

# session-detail 由 shared stop runner 显式执行,此处排除 legacy artifact check.
EXCLUDED_TARGETS = {'session-detail'}


def required_targets_for_stop(changed_files: list[str]) -> list[str]:
    """Return effective required targets after dominance and stop exclusions."""
    all_targets = effective_targets(required_quality_targets(changed_files))
    return [target for target in all_targets if target not in EXCLUDED_TARGETS]


def get_session_id() -> str | None:
    """Read the current agent session id for stop-hook target checks.

    Returns:
        Computed result.
    """
    return changed_file_utils.read_session_id(SESSION_ID_FILE)


def get_changed_files_for_session() -> list[str]:
    """获取当前 session 的变更文件列表.

    Returns:
        Computed result.
    """
    session_id = get_session_id()
    return changed_file_utils.collect_changed_files(
        session_id,
        include_git=True,
        repo_root=REPO_ROOT,
        changed_files_path=CHANGED_FILES,
    )


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
    summary = QUALITY_DIR / change_id / f'quality-gate-summary.{target}.json'

    if not summary.exists():
        expected = str(summary)
        existing = find_existing_summaries()
        existing_rel = [str(p.relative_to(REPO_ROOT)) for p in existing] if existing else ['无']

        msg_parts = [
            f'缺少 {target} quality artifact',
            f'  expected: {expected}',
            f'  change-id: {change_id}',
            f'  agent-log-dir: {AGENT_LOG_DIR}',
            f'  required targets: {sorted(required_targets_for_stop(get_changed_files_for_session()))}',
            f'  actual found summaries: {", ".join(existing_rel)}',
        ]
        return False, '\n'.join(msg_parts)

    try:
        data = json.loads(summary.read_text(encoding='utf-8'))
        status = str(data.get('status', '')).upper()
        if status != 'PASS':
            return (
                False,
                f'{target} quality artifact 状态为 {status}(文件:{summary.relative_to(REPO_ROOT)})',
            )
        return True, f'{target} quality gate PASS(文件:{summary.relative_to(REPO_ROOT)})'
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

    targets = required_targets_for_stop(changed_files)

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
