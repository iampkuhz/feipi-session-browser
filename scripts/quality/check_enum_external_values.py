#!/usr/bin/env python3
"""Enum 外部值守卫检查脚本。

扫描共享 Java 模块中的 enum 声明，验证对外暴露的枚举都具备显式外部值模式：
  - 拥有 ``private final String value`` 字段
  - 拥有 ``public static <Enum> fromValue(String)`` 工厂方法

仅使用 Python 标准库。退出码：
  0 — 所有对外枚举合规
  1 — 存在缺失外部值的枚举
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

#: 需要扫描的模块及其 src/main/java 根目录（相对于仓库根）。
SCAN_MODULES: list[str] = [
    "java/core-domain/src/main/java",
    "java/query-api/src/main/java",
    "java/source-spi/src/main/java",
]

#: 内部枚举，不要求外部值模式。
INTERNAL_ENUMS: set[str] = {
    "SourceOutcome",
}

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class EnumInfo:
    """一个 Java enum 的扫描结果。"""

    fqn: str
    file_path: str
    has_value_field: bool
    has_get_value: bool
    has_from_value: bool
    constants: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 扫描逻辑
# ---------------------------------------------------------------------------

_ENUM_DECL = re.compile(
    r"(?:public\s+)?(?:@\w+(?:\([^)]*\))?\s+)*enum\s+(\w+)"
)

_VALUE_FIELD = re.compile(
    r"(?:private\s+final\s+String\s+(?:value|columnName|sortKey)\b)"
)

_GET_VALUE = re.compile(
    r"(?:public\s+String\s+getValue\s*\(\s*\))"
)

_FROM_VALUE = re.compile(
    r"(?:public\s+static\s+\w+\s+fromValue\s*\(\s*String\s+\w*\s*\))"
)

_FROM_STRING = re.compile(
    r"(?:public\s+static\s+\w+\s+fromString\s*\(\s*String\s+\w*\s*\))"
)


def _find_repo_root() -> Path:
    """从脚本位置推断仓库根目录。"""
    script = Path(__file__).resolve()
    # scripts/quality/check_enum_external_values.py -> repo root
    return script.parent.parent.parent


def _scan_file(file_path: Path, module_root: str) -> EnumInfo | None:
    """解析单个 Java 文件，提取 enum 信息。"""
    text = file_path.read_text(encoding="utf-8")
    match = _ENUM_DECL.search(text)
    if not match:
        return None

    enum_name = match.group(1)
    # 推断包名
    pkg_match = re.search(r"package\s+([\w.]+)\s*;", text)
    package = pkg_match.group(1) if pkg_match else "<unknown>"
    fqn = f"{package}.{enum_name}"

    return EnumInfo(
        fqn=fqn,
        file_path=str(file_path),
        has_value_field=bool(_VALUE_FIELD.search(text)),
        has_get_value=bool(_GET_VALUE.search(text)),
        has_from_value=bool(_FROM_VALUE.search(text) or _FROM_STRING.search(text)),
    )


def scan_all(repo_root: Path) -> list[EnumInfo]:
    """扫描所有配置模块中的 enum 声明。"""
    results: list[EnumInfo] = []
    for module in SCAN_MODULES:
        module_dir = repo_root / module
        if not module_dir.exists():
            continue
        for java_file in sorted(module_dir.rglob("*.java")):
            info = _scan_file(java_file, module)
            if info is not None:
                results.append(info)
    return results


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def _is_external(enum_info: EnumInfo) -> bool:
    """判断枚举是否为对外暴露。"""
    simple_name = enum_info.fqn.rsplit(".", 1)[-1]
    return simple_name not in INTERNAL_ENUMS


def report(enums: list[EnumInfo]) -> tuple[list[EnumInfo], list[EnumInfo]]:
    """生成合规与不合规枚举列表。"""
    compliant: list[EnumInfo] = []
    violations: list[EnumInfo] = []
    for e in enums:
        if not _is_external(e):
            continue
        if e.has_value_field and e.has_from_value:
            compliant.append(e)
        else:
            violations.append(e)
    return compliant, violations


def main() -> int:
    repo_root = _find_repo_root()
    enums = scan_all(repo_root)

    if not enums:
        print("ERROR: 未找到任何 enum 声明。请检查扫描路径。")
        return 1

    compliant, violations = report(enums)

    print(f"扫描到 {len(enums)} 个枚举，其中 {len(compliant)} 个对外枚举合规。")
    print()

    if violations:
        print("=== 缺失外部值模式的对外枚举 ===")
        for v in violations:
            missing = []
            if not v.has_value_field:
                missing.append("value 字段")
            if not v.has_from_value:
                missing.append("fromValue/fromString 方法")
            print(f"  FAIL  {v.fqn}")
            print(f"        缺失: {', '.join(missing)}")
            print(f"        文件: {v.file_path}")
        print()
        print(f"共 {len(violations)} 个枚举不合规。")
        return 1

    print("所有对外枚举均具备显式外部值模式。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
