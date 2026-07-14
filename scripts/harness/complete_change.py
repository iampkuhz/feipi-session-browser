#!/usr/bin/env python3
"""负责旧 completion 命令的薄适配；不负责业务，委托 ``change.py on-stop``。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_runtime.change.candidate import collect_manifest  # noqa: E402
from scripts.harness.change import main as change_main  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """解析旧参数并保留兼容 guard；不运行收口步骤。"""
    parser = argparse.ArgumentParser(description='Compatibility facade for change.py on-stop')
    parser.add_argument('--repo-root')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--message', required=True)
    parser.add_argument('--file', action='append', default=[])
    parser.add_argument('--expect-manifest-hash', default='')
    parser.add_argument('--expect-candidate-tree', default='')
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """校验旧路径参数后委托统一 CLI；不自行 stage、Gate 或 commit。"""
    args = build_parser().parse_args(argv)
    repo = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    manifest = collect_manifest(repo)
    # 旧 --file 不再是安全边界，仅作为兼容 TOCTOU guard；正常调用不需要手拼路径。
    if args.file and tuple(sorted(set(args.file))) != manifest.paths:
        parser = build_parser()
        parser.error('legacy --file values do not match automatic exact manifest')
    command = [
        '--repo-root',
        str(repo),
        'on-stop',
        '--run-id',
        args.run_id,
        '--message',
        args.message,
        '--expect-manifest-hash',
        args.expect_manifest_hash or manifest.manifest_hash,
    ]
    if args.expect_candidate_tree:
        command.extend(['--expect-candidate-tree', args.expect_candidate_tree])
    return change_main(command)


if __name__ == '__main__':
    raise SystemExit(main())
