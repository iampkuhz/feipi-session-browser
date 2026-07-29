#!/usr/bin/env python3
"""本模块负责执行 `validate_active_change` 对应的确定性仓库检查。

不负责修改业务代码；由 OpenSpec 命令行或 required Gate 调用。"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path


def validate_change(change_id: str) -> list[str]:
    """验证当前工作目录下指定 change 的必需文件与 specs 目录。"""
    root = Path.cwd()
    change_dir = root / 'openspec' / 'changes' / change_id
    errors: list[str] = []

    if not change_dir.is_dir():
        return [f'Change directory not found: openspec/changes/{change_id}']

    required_files = ['proposal.md', 'design.md', 'tasks.md']
    for fname in required_files:
        if not (change_dir / fname).exists():
            errors.append(f'Missing required file: openspec/changes/{change_id}/{fname}')

    specs_dir = change_dir / 'specs'
    if not specs_dir.is_dir():
        errors.append(f'Missing directory: openspec/changes/{change_id}/specs/')
    else:
        spec_files = list(specs_dir.rglob('*.md'))
        # 过滤 README 等不属于规范正文的文件。
        if not spec_files:
            errors.append(f'No spec.md files found under openspec/changes/{change_id}/specs/')

    return errors


def run_self_test() -> bool:
    """在临时目录运行缺失、完整和不存在三类内嵌契约场景。"""
    tmp_root = Path(tempfile.mkdtemp(prefix='openspec_selftest_'))
    change_dir = tmp_root / 'openspec' / 'changes' / 'test-change'
    specs_dir = change_dir / 'specs'

    try:
        # 先证明空 change 会 fail-closed，再补齐文件验证成功路径。
        (change_dir / 'specs').mkdir(parents=True)
        errors = validate_change_at_root('test-change', tmp_root)
        if not errors:
            print('  FAIL: expected errors for empty change, got none')
            return False
        print(f'  PASS: detected missing files ({len(errors)} errors)')

        for fname in ['proposal.md', 'design.md', 'tasks.md']:
            (change_dir / fname).write_text(f'# {fname}\n')
        (specs_dir / 'spec.md').write_text('# spec\n')

        errors = validate_change_at_root('test-change', tmp_root)
        if errors:
            print(f'  FAIL: expected no errors for complete change, got: {errors}')
            return False
        print('  PASS: complete change validates clean')

        errors = validate_change_at_root('no-such-change', tmp_root)
        if not errors:
            print('  FAIL: expected error for non-existent change')
            return False
        print('  PASS: detected non-existent change')

        return True
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def validate_change_at_root(change_id: str, root: Path) -> list[str]:
    """在显式仓库根目录验证 change，供 self-test 隔离真实工作区。"""
    change_dir = root / 'openspec' / 'changes' / change_id
    errors: list[str] = []

    if not change_dir.is_dir():
        return [f'Change directory not found: openspec/changes/{change_id}']

    required_files = ['proposal.md', 'design.md', 'tasks.md']
    for fname in required_files:
        if not (change_dir / fname).exists():
            errors.append(f'Missing required file: openspec/changes/{change_id}/{fname}')

    specs_dir = change_dir / 'specs'
    if not specs_dir.is_dir():
        errors.append(f'Missing directory: openspec/changes/{change_id}/specs/')
    else:
        spec_files = list(specs_dir.rglob('*.md'))
        if not spec_files:
            errors.append(f'No spec.md files found under openspec/changes/{change_id}/specs/')

    return errors


def main() -> None:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    parser = argparse.ArgumentParser(description='Validate active OpenSpec change structure')
    parser.add_argument('--change-id', help='Change ID to validate')
    parser.add_argument('--self-test', action='store_true', help='Run self-test and exit')
    args = parser.parse_args()

    if args.self_test:
        print('Running self-test...')
        ok = run_self_test()
        if ok:
            print('self-test: PASS')
            sys.exit(0)
        else:
            print('self-test: FAIL')
            sys.exit(1)

    if not args.change_id:
        parser.error('either --change-id or --self-test is required')

    errors = validate_change(args.change_id)
    if errors:
        print(f"Validation FAILED for change '{args.change_id}':")
        for e in errors:
            print(f'  - {e}')
        sys.exit(1)
    else:
        print(f"Validation PASS for change '{args.change_id}'")
        sys.exit(0)


if __name__ == '__main__':
    main()
