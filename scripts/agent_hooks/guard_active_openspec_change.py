#!/usr/bin/env python3
"""提供 guard active OpenSpec change 脚本能力。"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks import paths as runtime_paths  # noqa: E402

# ---------------------------------------------------------------------------
# 配置项。
# ---------------------------------------------------------------------------

PROTECTED_ROOTS = [
    'CLAUDE.md',
    'AGENTS.md',
    'openspec',
    '.claude',
    '.codex',
    '.qoder',
    'scripts',
    'harness',
    'src',
]

# 路径 that are part of *creating* a change - 始终 allowed even 如果 under。
CREATION_EXCEPTIONS = [
    'openspec/changes',
    'tmp/active_change.json',
]

ACTIVE_CHANGE_FILE = 'tmp/active_change.json'
REQUIRED_CHANGE_FILES = ('proposal.md', 'design.md', 'tasks.md')


# 解析target。
def resolve_target(target: str, repo_root: Path) -> Path:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        repo_root: 仓库根目录。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    p = Path(target)
    if not p.is_absolute():
        p = repo_root / p
    return p.resolve()


# 判断是否protected。
def is_protected(target_resolved: Path, repo_root: Path) -> bool:
    """参数：
        target_resolved: Absolute 路径到evaluate。
        repo_root: 仓库根目录。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    # Exact match用于repo-level 文件 (CLAUDE.md, AGENTS.md)。
    for root_name in PROTECTED_ROOTS:
        candidate = repo_root / root_name
        candidate = candidate.resolve()
        if target_resolved == candidate:
            return True
        if candidate.is_dir() and (str(target_resolved) + '/').startswith(str(candidate) + '/'):
            return True
    return False


# 判断是否creation exception。
def is_creation_exception(target_resolved: Path, repo_root: Path) -> bool:
    """参数：
        target_resolved: Absolute 路径到evaluate。
        repo_root: 仓库根目录。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    for exc_rel in CREATION_EXCEPTIONS:
        candidate = (repo_root / exc_rel).resolve()
        if (str(target_resolved) + '/').startswith(str(candidate) + '/'):
            return True
        if target_resolved == candidate:
            return True
    return False


# 检查active change。
def check_active_change(repo_root: Path) -> tuple[bool, str]:  # noqa: PLR0911
    """参数：
        repo_root: 仓库根目录。

    返回：
        由success flag 和 human-读取able 状态 或 阻断 message.组成的 tuple。
    """
    identity = runtime_paths.identity_from_values()
    if identity.has_session:
        candidates = runtime_paths.build_paths(repo_root, identity).active_change_candidates
    else:
        candidates = [repo_root / ACTIVE_CHANGE_FILE]

    active_change_path = next((path for path in candidates if path.exists()), candidates[0])
    if not active_change_path.exists():
        return False, (
            f'BLOCKED: No active OpenSpec change ({active_change_path} not found).\n'
            'Create a change with /change before editing protected files.'
        )

    # 校验 JSON。
    try:
        data = json.loads(active_change_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return False, (
            f'BLOCKED: {active_change_path} is not valid JSON: {exc}\n'
            'Fix or recreate the active change file.'
        )

    change_id = data.get('change_id', '')
    if not change_id:
        return False, (
            f"BLOCKED: {active_change_path} is missing 'change_id'.\n"
            'Recreate the active change file with a valid change_id.'
        )

    # 检查a matching non-archive 目录 exists under openspec/changes/。
    changes_dir = repo_root / 'openspec' / 'changes'
    if not changes_dir.is_dir():
        return False, (
            f"BLOCKED: openspec/changes/ directory is missing.\nCannot verify change '{change_id}'."
        )

    matching = [
        d
        for d in changes_dir.iterdir()
        if d.is_dir() and d.name != 'archive' and d.name == change_id
    ]
    if not matching:
        return False, (
            f"BLOCKED: No non-archive directory 'openspec/changes/{change_id}/' found.\n"
            f"active_change.json references '{change_id}', but no matching change "
            "directory exists.\n"
            'Create the change or fix active_change.json.'
        )

    change_dir = matching[0]
    missing = [name for name in REQUIRED_CHANGE_FILES if not (change_dir / name).is_file()]
    if missing:
        return False, (
            f"BLOCKED: Active change '{change_id}' is incomplete; missing "
            f'{", ".join(missing)}.\n'
            f'Before editing protected files, complete openspec/changes/{change_id}/ '
            'or run scripts/openspec/create_active_change.py with the intended change id.'
        )

    return True, f"Active change '{change_id}' verified."


# 维护保护。
def guard(target: str, repo_root: Path | None = None) -> int:
    """参数：
        target: 文件路径 requested by editing tool。
        repo_root: 可选repo root override用于self-tests。

    返回：
        进程退出码。
    """
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = repo_root.resolve()

    target_resolved = resolve_target(target, repo_root)

    if is_creation_exception(target_resolved, repo_root):
        return 0

    # Non-protected 文件 are 始终 allowed。
    if not is_protected(target_resolved, repo_root):
        return 0

    ok, message = check_active_change(repo_root)
    if not ok:
        print(message, file=sys.stderr)
        return 1

    return 0


# 运行self test。
def run_self_test() -> int:  # noqa: PLR0915
    """返回：
        进程退出码。
    """
    results: list[tuple[str, bool, str]] = []

    with tempfile.TemporaryDirectory(prefix='guard_self_test_') as tmpdir:
        tmp = Path(tmpdir)

        (tmp / 'openspec' / 'changes' / 'archive').mkdir(parents=True)
        (tmp / 'tmp').mkdir(parents=True)
        for r in ['scripts', 'src']:
            (tmp / r).mkdir(parents=True)
        (tmp / 'CLAUDE.md').touch()
        (tmp / 'AGENTS.md').touch()
        (tmp / 'non-protected.txt').touch()

        target_a = str(tmp / 'CLAUDE.md')
        ret_a = guard(target_a, repo_root=tmp)
        results.append(
            ('no_active_change -> BLOCK protected file', ret_a == 1, f'exit={ret_a} (expected 1)')
        )

        active_change_data = {
            'change_id': 'test-change',
            'change_path': 'openspec/changes/test-change/',
        }
        (tmp / ACTIVE_CHANGE_FILE).write_text(
            json.dumps(active_change_data, indent=2), encoding='utf-8'
        )
        change_b = tmp / 'openspec' / 'changes' / 'test-change'
        change_b.mkdir(parents=True)
        for required in REQUIRED_CHANGE_FILES:
            (change_b / required).write_text(f'# {required}\n', encoding='utf-8')

        target_b = str(tmp / 'src' / 'main.py')
        ret_b = guard(target_b, repo_root=tmp)
        results.append(
            (
                'valid_active_change -> ALLOW protected file',
                ret_b == 0,
                f'exit={ret_b} (expected 0)',
            )
        )

        # Sub-test C: Non-protected 文件 is 始终 ALLOW。
        target_c = str(tmp / 'non-protected.txt')
        ret_c = guard(target_c, repo_root=tmp)
        results.append(('non_protected_file -> ALLOW', ret_c == 0, f'exit={ret_c} (expected 0)'))

        target_d = '/tmp/guard_test_file.txt'
        ret_d = guard(target_d, repo_root=tmp)
        results.append(('external_file -> ALLOW', ret_d == 0, f'exit={ret_d} (expected 0)'))

        (tmp / ACTIVE_CHANGE_FILE).write_text(
            json.dumps({'change_id': 'nonexistent-change'}, indent=2), encoding='utf-8'
        )
        target_e = str(tmp / 'CLAUDE.md')
        ret_e = guard(target_e, repo_root=tmp)
        results.append(
            (
                'mismatched_change_id -> BLOCK protected file',
                ret_e == 1,
                f'exit={ret_e} (expected 1)',
            )
        )

        (tmp / ACTIVE_CHANGE_FILE).write_text('not json {{{', encoding='utf-8')
        target_f = str(tmp / 'scripts' / 'test.py')
        ret_f = guard(target_f, repo_root=tmp)
        results.append(
            ('invalid_json -> BLOCK protected file', ret_f == 1, f'exit={ret_f} (expected 1)')
        )

        (tmp / ACTIVE_CHANGE_FILE).write_text(
            json.dumps({'change_id': 'test-change'}, indent=2), encoding='utf-8'
        )
        target_g = str(tmp / 'openspec' / 'changes' / 'test-change' / 'specs' / 'test.md')
        ret_g = guard(target_g, repo_root=tmp)
        results.append(
            (
                'creation_exception -> ALLOW under openspec/changes/',
                ret_g == 0,
                f'exit={ret_g} (expected 0)',
            )
        )

        target_h = str(tmp / 'tmp' / 'active_change.json')
        ret_h = guard(target_h, repo_root=tmp)
        results.append(
            (
                'creation_exception -> ALLOW tmp/active_change.json',
                ret_h == 0,
                f'exit={ret_h} (expected 0)',
            )
        )

    # 报告输出。
    all_pass = True
    print(f'\n{"=" * 60}')
    print('self-test results')
    print(f'{"=" * 60}')
    for name, passed, detail in results:
        status = 'PASS' if passed else 'FAIL'
        if not passed:
            all_pass = False
        print(f'  [{status}] {name} - {detail}')
    print(f'{"=" * 60}')
    print(f'  {sum(1 for _, p, _ in results if p)}/{len(results)} passed')
    print(f'{"=" * 60}')

    return 0 if all_pass else 1


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(
        description='PreToolUse hook: block protected writes without active OpenSpec change.'
    )
    parser.add_argument(
        'target',
        nargs='?',
        default=None,
        help='Target file path to check.',
    )
    parser.add_argument(
        '--self-test',
        action='store_true',
        help='Run self-tests and exit.',
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.target:
        # 没有target provided; allow (guard is 不 applicable 不带 a target)。
        return 0

    ret = guard(args.target)
    if ret != 0:
        return ret
    return 0


if __name__ == '__main__':
    sys.exit(main())
