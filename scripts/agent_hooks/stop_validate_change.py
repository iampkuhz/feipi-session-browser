#!/usr/bin/env python3
"""提供 stop validate change 脚本能力。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置项。
# ---------------------------------------------------------------------------

PROTECTED_ROOTS = [
    'CLAUDE.md',
    'AGENTS.md',
    'openspec/',
    '.claude/',
    '.codex/',
    '.qoder/',
    'scripts/',
    'harness/',
    'src/',
]

ACTIVE_CHANGE_FILE = Path('tmp/active_change.json')
EVIDENCE_DIR = Path('tmp/task-evidence')

# 必需 文件 inside openspec/changes/<change-id>/。
REQUIRED_CHANGE_FILES = ['proposal.md', 'design.md', 'tasks.md']
EXIT_ALLOW = 0
EXIT_BLOCK = 2


# 维护repo 根目录。
def _repo_root() -> Path:
    """返回：
        Absolute 路径到当前 working 目录。
    """
    return Path.cwd().resolve()


# 判断是否存在uncommitted changes。
def has_uncommitted_changes(roots: list[str] | None = None) -> bool:
    """参数：
        roots: 可选protected roots以检查 instead of 默认 set。

    返回：
        当git reports changes 或 git 状态 cannot be trusted.时返回 true。
    """
    if roots is None:
        roots = PROTECTED_ROOTS
    root = _repo_root()
    try:
        result = subprocess.run(
            ['git', 'status', '--short', *roots],
            capture_output=True,
            check=False,
            text=True,
            cwd=root,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return True


# 加载active change。
def load_active_change() -> dict | None:
    """返回：
        已解析的active change metadata, 或 None 当 unavailable。
    """
    root = _repo_root()
    p = root / ACTIVE_CHANGE_FILE
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


# 维护change id active。
def change_id_from_active(active: dict | None) -> str | None:
    """参数：
        active: 已解析的active change metadata, 如果 可用。

    返回：
        Change id 字符串, 或 None 当 metadata is 缺失 it。
    """
    if active:
        return active.get('change_id')
    return None


# 维护change 目录 exists。
def change_dir_exists(change_id: str) -> bool:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        当openspec/changes/<change-id>/ exists.时返回 true。
    """
    return (_repo_root() / 'openspec' / 'changes' / change_id).is_dir()


# 维护必需 文件 存在。
def required_files_present(change_id: str) -> list[str]:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        Names of 必需 文件 that are 不 present。
    """
    base = _repo_root() / 'openspec' / 'changes' / change_id
    missing = []
    for name in REQUIRED_CHANGE_FILES:
        if not (base / name).is_file():
            missing.append(name)
    return missing


# 维护evidence 文件。
def evidence_file(change_id: str) -> Path:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    return _repo_root() / EVIDENCE_DIR / f'{change_id}.jsonl'


# 判断是否存在evidence entries。
def has_evidence_entries(change_id: str) -> bool:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    ef = evidence_file(change_id)
    if not ef.is_file():
        return False
    try:
        text = ef.read_text(encoding='utf-8').strip()
        return bool(text)  # non-empty
    except OSError:
        return False

# 判断是否存在completed 任务。
def has_completed_tasks(change_id: str) -> bool:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        当tasks.md contains at least one checked task item.时返回 true。
    """
    tasks = _repo_root() / 'openspec' / 'changes' / change_id / 'tasks.md'
    if not tasks.is_file():
        return False
    content = tasks.read_text(encoding='utf-8')
    # 查找常见 Markdown 已完成任务标记。
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith('- [x]') or stripped.startswith('* [x]'):
            return True
    return False

# 维护修复 消息。
def repair_messages(change_id: str | None = None) -> list[str]:
    """参数：
        change_id: 已知的活跃 OpenSpec change identifier。

    返回：
        给 agent 执行的有序修复步骤。
    """
    target = f" '{change_id}'" if change_id else ''
    return [
        'Continue instead of stopping: repair the OpenSpec state, then retry stop.',
        f'  1. Ensure active_change.json points to the intended active change{target}.',
        '  2. Ensure proposal.md, design.md, and tasks.md exist under that change.',
        (
            '  3. Record or preserve edit evidence in '
            'identity-scoped task-evidence/<change-id>.jsonl.'
        ),
        '  4. Mark completed tasks in tasks.md before final stop.',
    ]


# 验证输入契约。
def validate() -> tuple[int, list[str]]:  # noqa: PLR0911
    """返回：
        进程退出码和可读验证消息。
    """
    messages: list[str] = []

    # 紧急旁路保持兼容。
    if os.environ.get('FEIPI_SKIP_STOP_HOOK', '').strip() == '1':
        messages.append('EMERGENCY BYPASS: FEIPI_SKIP_STOP_HOOK=1 detected, skipping validation.')
        return 0, messages

    # 没有受保护改动时允许干净停止。
    if not has_uncommitted_changes():
        messages.append('No protected changes detected. Clean stop.')
        return 0, messages

    messages.append('Protected changes detected. Validating OpenSpec change completeness ...')

    # 检查 active_change.json。
    active = load_active_change()
    if active is None:
        messages.append(
            'BLOCK: protected files changed without active change '
            '(active_change.json missing or invalid).'
        )
        messages.extend(repair_messages())
        return EXIT_BLOCK, messages

    cid = change_id_from_active(active)
    if not cid:
        messages.append("BLOCK: active_change.json missing 'change_id'.")
        messages.extend(repair_messages())
        return EXIT_BLOCK, messages

    # 检查 change 目录是否存在。
    if not change_dir_exists(cid):
        messages.append(f'BLOCK: openspec/changes/{cid}/ directory not found.')
        messages.extend(repair_messages(cid))
        return EXIT_BLOCK, messages

    # 检查必需文件。
    missing = required_files_present(cid)
    if missing:
        messages.append(
            f"WARN/BLOCK: change '{cid}' is missing required files: {', '.join(missing)}"
        )

    # 检查 evidence。
    ef = evidence_file(cid)
    if not has_evidence_entries(cid):
        messages.append(f'WARN/BLOCK: no evidence entries in {ef.relative_to(_repo_root())}')

    # 检查已完成任务，仅作为提示信息。
    if has_completed_tasks(cid):
        messages.append('  tasks.md: some tasks marked complete (change in progress).')
    else:
        messages.append('  tasks.md: no tasks marked complete yet.')

    # 缺少必需文件或 evidence 时必须阻断。
    if missing or not has_evidence_entries(cid):
        messages.append(
            'Result: BLOCK - protected changes exist but change/evidence is incomplete.'
        )
        messages.extend(repair_messages(cid))
        return EXIT_BLOCK, messages

    messages.append(f"Result: ALLOW - change '{cid}' has required files and evidence.")
    return 0, messages


# 运行self test。
def _run_self_test() -> int:  # noqa: PLR0915
    """返回：
        全部自测通过时返回 0，否则返回 1。

    说明：
        覆盖无改动、缺失活跃变更、证据完整、紧急旁路和缺失必需文件场景。
    """
    results: list[tuple[str, bool, str]] = []

    # 维护检查。
    def check(name: str, condition: bool, detail: str = '') -> None:
        """参数：
            name: 便于阅读的断言名称。
            condition: 表示断言是否通过。
            detail: 失败诊断或计数详情。
        """
        passed = condition
        status = 'PASS' if passed else 'FAIL'
        results.append((name, passed, detail))
        print(f'  [{status}] {name}' + (f' -- {detail}' if detail else ''))

    with tempfile.TemporaryDirectory(prefix='stop_validate_test_') as tmpdir:
        tmp = Path(tmpdir)

        # 创建最小 git 仓库。
        subprocess.run(['git', 'init', '-q', str(tmp)], check=True, capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=tmp,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test'],
            cwd=tmp,
            check=True,
            capture_output=True,
        )

        # 创建初始文件和 commit。
        for p in [
            tmp / 'CLAUDE.md',
            tmp / 'AGENTS.md',
            tmp / 'README.md',
        ]:
            p.write_text('# test\n', encoding='utf-8')
        (tmp / 'openspec' / 'changes' / 'archive').mkdir(parents=True)
        (tmp / 'tmp').mkdir(parents=True)
        (tmp / 'src').mkdir(parents=True)
        (tmp / 'scripts').mkdir(parents=True)

        subprocess.run(['git', 'add', '.'], cwd=tmp, check=True, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'initial', '-q', '--allow-empty'],
            cwd=tmp,
            check=True,
            capture_output=True,
        )

        # 子用例 1：无受保护改动且无活跃变更时允许停止。
        print('Sub-test 1: no protected changes, no active change -> ALLOW')
        saved_cwd = Path.cwd()
        os.chdir(tmp)
        saved_skip = os.environ.pop('FEIPI_SKIP_STOP_HOOK', None)
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ['FEIPI_SKIP_STOP_HOOK'] = saved_skip
        check('exit code is 0 (ALLOW)', exit_code == 0, f'exit={exit_code}')

        # 子用例 2：存在受保护改动但无活跃变更时阻断。
        print('Sub-test 2: protected changes, no active change -> BLOCK')
        os.chdir(tmp)
        saved_skip = os.environ.pop('FEIPI_SKIP_STOP_HOOK', None)
        # 修改一个受保护文件。
        (tmp / 'CLAUDE.md').write_text('# modified\n', encoding='utf-8')
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ['FEIPI_SKIP_STOP_HOOK'] = saved_skip
        check('exit code is 2 (BLOCK)', exit_code == EXIT_BLOCK, f'exit={exit_code}')
        has_block_msg = any('BLOCK' in m or 'block' in m.lower() for m in msgs)
        check('message contains BLOCK', has_block_msg, 'messages: ' + '; '.join(msgs[:3]))

        # 子用例 3：受保护改动、活跃变更和 evidence 完整时允许。
        print('Sub-test 3: protected changes + active change + evidence -> ALLOW')
        os.chdir(tmp)
        saved_skip = os.environ.pop('FEIPI_SKIP_STOP_HOOK', None)
        # 配置活跃变更。
        (tmp / 'tmp' / 'active_change.json').write_text(
            json.dumps(
                {
                    'change_id': 'test-change-003',
                    'change_path': 'openspec/changes/test-change-003/',
                },
                indent=2,
            ),
            encoding='utf-8',
        )
        # 创建包含必需文件的 change 目录。
        cdir = tmp / 'openspec' / 'changes' / 'test-change-003'
        cdir.mkdir(parents=True)
        (cdir / 'proposal.md').write_text('# Proposal\n', encoding='utf-8')
        (cdir / 'design.md').write_text('# Design\n', encoding='utf-8')
        (cdir / 'tasks.md').write_text('- [x] Task 1\n- [ ] Task 2\n', encoding='utf-8')
        # 配置 evidence。
        evdir = tmp / 'tmp' / 'task-evidence'
        evdir.mkdir(parents=True)
        (evdir / 'test-change-003.jsonl').write_text(
            '{"ts":"2026-01-01T00:00:00Z","tool":"Edit","file_path":"CLAUDE.md","change_id":"test-change-003"}\n',
            encoding='utf-8',
        )
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ['FEIPI_SKIP_STOP_HOOK'] = saved_skip
        check('exit code is 0 (ALLOW)', exit_code == 0, f'exit={exit_code}')

        # 子用例 4：紧急旁路始终允许。
        print('Sub-test 4: emergency bypass (FEIPI_SKIP_STOP_HOOK=1) -> ALWAYS ALLOW')
        os.chdir(tmp)
        os.environ['FEIPI_SKIP_STOP_HOOK'] = '1'
        # 即使状态破损也应允许紧急旁路。
        # 移除 active_change，构造最坏情况。
        (tmp / 'tmp' / 'active_change.json').unlink()
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        os.environ.pop('FEIPI_SKIP_STOP_HOOK', None)
        check('exit code is 0 (ALLOW)', exit_code == 0, f'exit={exit_code}')
        has_bypass_msg = any('EMERGENCY BYPASS' in m or 'bypass' in m.lower() for m in msgs)
        check('message mentions bypass', has_bypass_msg, 'messages: ' + '; '.join(msgs[:2]))

        # 子用例 5：有活跃变更但缺少必需文件时阻断。
        print('Sub-test 5: protected changes + active change but missing required files -> BLOCK')
        os.chdir(tmp)
        saved_skip = os.environ.pop('FEIPI_SKIP_STOP_HOOK', None)
        # 重建活跃变更，但 change 目录不完整。
        (tmp / 'tmp' / 'active_change.json').write_text(
            json.dumps(
                {
                    'change_id': 'test-change-005',
                    'change_path': 'openspec/changes/test-change-005/',
                },
                indent=2,
            ),
            encoding='utf-8',
        )
        cdir5 = tmp / 'openspec' / 'changes' / 'test-change-005'
        cdir5.mkdir(parents=True)
        # 只创建 proposal.md，故意缺少 design.md 和 tasks.md。
        (cdir5 / 'proposal.md').write_text('# Proposal\n', encoding='utf-8')
        # 同时缺少 evidence。
        exit_code, msgs = validate()
        os.chdir(saved_cwd)
        if saved_skip is not None:
            os.environ['FEIPI_SKIP_STOP_HOOK'] = saved_skip
        check('exit code is 2 (BLOCK)', exit_code == EXIT_BLOCK, f'exit={exit_code}')
        has_block_msg = any('BLOCK' in m or 'block' in m.lower() or 'WARN' in m for m in msgs)
        check('message indicates incomplete', has_block_msg, 'messages: ' + '; '.join(msgs[:3]))

    # 结果汇总。
    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)
    all_pass = passed_count == total

    print(f'\n{"=" * 60}')
    print(f'self-test results: {passed_count}/{total} passed')
    print(f'{"=" * 60}')
    for name, passed, detail in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  [{status}] {name}' + (f' -- {detail}' if detail else ''))
    print(f'{"=" * 60}')

    return 0 if all_pass else 1


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        hook 调用的进程退出码。
    """
    parser = argparse.ArgumentParser(
        description='Stop/SubagentStop hook: validate OpenSpec change completeness.'
    )
    parser.add_argument(
        '--self-test',
        action='store_true',
        help='Run self-test suite and exit.',
    )
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    exit_code, messages = validate()
    for msg in messages:
        print(msg, file=sys.stderr if exit_code != 0 else sys.stdout)

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
