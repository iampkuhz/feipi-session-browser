#!/usr/bin/env python3
"""校验 ISSUE-BOARD.md 基本结构。只用 Python stdlib。"""

import pathlib
import sys

REQUIRED_STATUSES = [
    "NEW", "TRIAGED", "ASSIGNED", "IN_PROGRESS",
    "DONE", "DUPLICATE", "OUT_OF_SCOPE", "BLOCKED",
]

EXPECTED_HEADER = (
    "| Issue ID | 来源 | 摘要 | 优先级 | 状态 | 分配任务 | 验收标准 | 备注 |"
)

EXPECTED_SEPARATOR = "|---|---|---|---|---|---|---|---|"


def validate(path: pathlib.Path) -> list[str]:
    errors: list[str] = []

    if not path.exists():
        errors.append(f"文件不存在: {path}")
        return errors

    content = path.read_text(encoding="utf-8")

    # 1. 检查状态枚举段落
    if "## 状态枚举" not in content:
        errors.append("缺少 '## 状态枚举' 段落")
    else:
        for status in REQUIRED_STATUSES:
            if f"`{status}`" not in content:
                errors.append(f"状态枚举缺少: {status}")

    # 2. 检查问题表表头
    if "## 问题表" not in content:
        errors.append("缺少 '## 问题表' 段落")
    else:
        if EXPECTED_HEADER not in content:
            errors.append(f"问题表表头不匹配，期望: {EXPECTED_HEADER}")
        if EXPECTED_SEPARATOR not in content:
            errors.append("问题表缺少分隔行或分隔行格式不正确")

    # 3. 检查处理规则段落
    if "## 处理规则" not in content:
        errors.append("缺少 '## 处理规则' 段落")

    # 4. 检查数据行（如果有）列数正确
    lines = content.splitlines()
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped == EXPECTED_HEADER:
            in_table = True
            continue
        if in_table:
            if stripped == EXPECTED_SEPARATOR:
                continue
            if stripped.startswith("|"):
                cols = [c.strip() for c in stripped.split("|")]
                # split 后首尾为空串，有效列数 = len(cols) - 2
                if len(cols) - 2 != 8:
                    errors.append(f"表格行列数不为 8: {stripped}")
            else:
                in_table = False

    return errors


def main() -> int:
    board_path = pathlib.Path(__file__).resolve().parent.parent.parent / "harness" / "workflow" / "java-first-migration" / "ISSUE-BOARD.md"
    errs = validate(board_path)
    if errs:
        print("ISSUE-BOARD 校验失败:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("ISSUE-BOARD 校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
