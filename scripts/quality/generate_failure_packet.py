#!/usr/bin/env python3
"""失败包生成器。

当 autonomous 任务连续 3 轮修复失败时，生成失败包并记录上下文。

用法:
    python3 scripts/quality/generate_failure_packet.py --task-id 025 --task-name "无引用legacy alias删除" --error "3轮修复失败"
    python3 scripts/quality/generate_failure_packet.py --task-id 118 --task-name "失败包生成器验证" --error "模拟失败" --self-test

退出码:
    0 — 失败包生成成功（或 self-test 通过）
    1 — 生成失败
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FAILURE_DIR = REPO_ROOT / "tmp" / "v9-failure-packets"


def generate_failure_packet(task_id: str, task_name: str, error: str, extra: dict | None = None) -> Path:
    """生成失败包文件。"""
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{task_id}-{task_name}.md"
    packet_path = FAILURE_DIR / filename

    timestamp = datetime.now(timezone.utc).isoformat()

    # 收集当前 git 状态
    git_status = _safe_git_output(["git", "status", "--short"])
    git_log = _safe_git_output(["git", "log", "--oneline", "-3"])

    content = f"""# 失败包: 任务 {task_id}

## 基本信息

- **任务编号**: {task_id}
- **任务名称**: {task_name}
- **失败时间**: {timestamp}
- **失败原因**: {error}

## Git 状态

```
{git_status}
```

## 最近提交

```
{git_log}
```
"""

    if extra:
        content += "\n## 额外信息\n\n"
        for key, value in extra.items():
            content += f"- **{key}**: {value}\n"
        content += "\n"

    content += """## 处理建议

1. 检查失败原因是否可修复
2. 如可修复，手动修复后重新运行任务
3. 如不可修复，记录为非目标并在 MASTER.md 中标记
"""

    packet_path.write_text(content, encoding="utf-8")
    return packet_path


def _safe_git_output(cmd: list[str]) -> str:
    """安全地获取 git 输出，失败时返回占位符。"""
    try:
        import subprocess
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        return (result.stdout or "").strip() or "(无输出)"
    except Exception:
        return "(git 命令执行失败)"


def _self_test() -> int:
    """Self-test: 生成模拟失败包并验证完整性。"""
    import tempfile
    import json

    test_dir = Path(tempfile.mkdtemp())
    test_failure_dir = test_dir / "v9-failure-packets"
    test_failure_dir.mkdir(parents=True, exist_ok=True)

    # Override the global for testing
    global FAILURE_DIR
    old_dir = FAILURE_DIR
    FAILURE_DIR = test_failure_dir

    try:
        packet = generate_failure_packet(
            task_id="test-001",
            task_name="self-test",
            error="模拟测试失败",
            extra={"test": "true", "attempt": "1"},
        )

        # 验证文件存在
        assert packet.exists(), f"失败包未生成: {packet}"

        # 验证内容完整性
        text = packet.read_text(encoding="utf-8")
        assert "test-001" in text, "缺少任务编号"
        assert "self-test" in text, "缺少任务名称"
        assert "模拟测试失败" in text, "缺少失败原因"
        assert "**test**: true" in text, "缺少额外信息"
        assert "Git 状态" in text, "缺少 Git 状态"
        assert "最近提交" in text, "缺少最近提交"
        assert "处理建议" in text, "缺少处理建议"

        print("  PASS: failure packet generation self-test")
        return 0
    finally:
        FAILURE_DIR = old_dir
        # Clean up
        import shutil
        shutil.rmtree(test_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="失败包生成器")
    parser.add_argument("--task-id", default=None, help="任务编号")
    parser.add_argument("--task-name", default=None, help="任务名称")
    parser.add_argument("--error", default=None, help="失败原因")
    parser.add_argument("--self-test", action="store_true", help="运行自测")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    if not args.task_id or not args.task_name or not args.error:
        print("ERROR: 需要 --task-id, --task-name, --error")
        return 1

    packet = generate_failure_packet(args.task_id, args.task_name, args.error)
    print(f"failure packet: {packet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
