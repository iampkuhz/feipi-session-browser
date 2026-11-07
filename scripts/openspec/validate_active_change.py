#!/usr/bin/env python3
"""本模块负责执行 `validate_active_change` 对应的确定性仓库检查。

不负责修改业务代码；由 OpenSpec 命令行或 required Gate 调用。"""

import argparse
import re
import sys
from pathlib import Path


def validate_change_at_root(change_id: str, root: Path) -> list[str]:
    """在显式仓库根目录验证 change，不依赖全局 active change 指针。"""
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', change_id):
        return [f'Invalid change ID: {change_id}']
    change_dir = root / 'openspec' / 'changes' / change_id
    errors: list[str] = []

    if not change_dir.is_dir():
        return [f'Change directory not found: openspec/changes/{change_id}']

    for fname in ('proposal.md', 'tasks.md'):
        if not (change_dir / fname).is_file():
            errors.append(f'Missing required file: openspec/changes/{change_id}/{fname}')

    specs_dir = change_dir / 'specs'
    if not specs_dir.is_dir():
        errors.append(f'Missing directory: openspec/changes/{change_id}/specs/')
    else:
        if not any(path.is_file() for path in specs_dir.rglob('spec.md')):
            errors.append(f'No spec.md files found under openspec/changes/{change_id}/specs/')

    return errors


def main() -> None:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    parser = argparse.ArgumentParser(description='Validate active OpenSpec change structure')
    parser.add_argument('--change-id', required=True, help='Change ID to validate')
    args = parser.parse_args()
    errors = validate_change_at_root(args.change_id, Path.cwd())
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
