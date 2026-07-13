#!/usr/bin/env python3
"""负责运行最小合成 Session contract Gate；不负责生成样本；由质量检查入口调用。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_gate(repo_root: Path) -> int:
    """运行真实 Java source adapter/normalization contract，透传失败语义。"""
    gradlew = repo_root / 'gradlew'
    if not gradlew.exists():
        print(f'sessionSamples: BLOCKED gradlew 不存在: {gradlew}', file=sys.stderr)
        return 2
    proc = subprocess.run(
        [str(gradlew), ':java:tests:contracts:sampleIntegrationTest', '--no-daemon'],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout or ''
    print(output if proc.returncode == 0 else output[-4000:], end='')
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    """解析仓库根目录并执行 contract Gate。"""
    parser = argparse.ArgumentParser(description='Run synthetic session sample quality gate')
    parser.add_argument('--repo-root', default='.', help='Repository root')
    args = parser.parse_args(argv)
    return run_gate(Path(args.repo_root).resolve())


if __name__ == '__main__':
    raise SystemExit(main())
