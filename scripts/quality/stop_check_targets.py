#!/usr/bin/env python3
"""Stop hook: 检查所有 必需 quality targets 是否已有 PASS artifact。"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks.classify import effective_targets, required_quality_targets  # noqa: E402
from scripts.claude_hooks import paths as runtime_paths  # noqa: E402
from scripts.quality import changed_files as changed_file_utils  # noqa: E402

IDENTITY = runtime_paths.identity_from_values()
AGENT_LOG_DIR = runtime_paths.agent_log_dir(REPO_ROOT, IDENTITY)
CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
QUALITY_DIR = (
    runtime_paths.quality_dir(REPO_ROOT, IDENTITY)
    if IDENTITY.has_session
    else REPO_ROOT / 'tmp' / 'quality'
)
SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'

# session-detail 由 shared stop runner 显式执行,此处排除 legacy artifact check.
EXCLUDED_TARGETS = {'session-detail'}


# 维护必需 targets stop。
def required_targets_for_stop(changed_files: list[str]) -> list[str]:
    """参数：
        changed_files: 待检查的文件列表。

    返回：
        结果列表。
    """
    all_targets = effective_targets(required_quality_targets(changed_files))
    return [target for target in all_targets if target not in EXCLUDED_TARGETS]


# 读取session id。
def get_session_id() -> str | None:
    """返回：
        Computed 结果。
    """
    return changed_file_utils.read_session_id(SESSION_ID_FILE)


# 读取changed-files 文件 session。
def get_changed_files_for_session() -> list[str]:
    """返回：
        Computed 结果。
    """
    if IDENTITY.has_session:
        log_dirs = runtime_paths.session_log_dirs(
            REPO_ROOT,
            IDENTITY,
            include_agents=not IDENTITY.is_agent,
        )
        return changed_file_utils.read_recorded_changed_files_from_paths(
            [path / 'changed-files.jsonl' for path in log_dirs],
            IDENTITY.raw_session_id,
            agent_id=IDENTITY.raw_agent_id or None,
        )
    session_id = get_session_id()
    return changed_file_utils.collect_changed_files(
        session_id,
        include_git=True,
        repo_root=REPO_ROOT,
        changed_files_path=CHANGED_FILES,
        base_commit_file=AGENT_LOG_DIR / 'base-commit.txt',
    )


# 解析change id。
def resolve_change_id() -> str:
    """返回：
        Computed 结果。
    """
    if IDENTITY.has_session:
        candidates = runtime_paths.build_paths(REPO_ROOT, IDENTITY).active_change_candidates
    else:
        candidates = [runtime_paths.legacy_active_change_path(REPO_ROOT)]
    for active_change in candidates:
        if not active_change.exists():
            continue
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            cid = data.get('change_id') or data.get('changeId') or ''
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            continue
    return 'unknown'


# 查找existing summaries。
def find_existing_summaries() -> list[Path]:
    """返回：
        Computed 结果。
    """
    summaries: list[Path] = []
    if QUALITY_DIR.exists():
        for change_dir in sorted(QUALITY_DIR.iterdir()):
            if change_dir.is_dir():
                for f in sorted(change_dir.iterdir()):
                    if f.name.startswith('quality-gate-summary.') and f.name.endswith('.json'):
                        summaries.append(f)
    return summaries


# 检查target artifact。
def check_target_artifact(target: str, change_id: str) -> tuple[bool, str]:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        change_id: 当前 OpenSpec change id。

    返回：
        Computed 结果。
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


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        Computed 结果。
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
