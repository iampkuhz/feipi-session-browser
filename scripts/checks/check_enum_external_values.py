#!/usr/bin/env python3
"""Enum 外部值守卫检查脚本。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'java/**/src/main/java/**/*.java',
]

#: 需要扫描的模块及其 src/main/java 根目录（相对于仓库根）。
SCAN_MODULES: list[str] = [
    "java/core-domain/src/main/java",
    "java/application/src/main/java/com/feipi/session/browser/query/api",
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
    """---------------------------------------------------------------------------"""

    fqn: str
    file_path: str
    has_value_field: bool
    has_get_value: bool
    has_from_value: bool
    constants: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 扫描逻辑
# ---------------------------------------------------------------------------

_ENUM_DECL = re.compile(r"(?:public\s+)?(?:@\w+(?:\([^)]*\))?\s+)*enum\s+(\w+)")

_VALUE_FIELD = re.compile(r"(?:private\s+final\s+String\s+(?:value|columnName|sortKey)\b)")

_GET_VALUE = re.compile(r"(?:public\s+String\s+getValue\s*\(\s*\))")

_FROM_VALUE = re.compile(r"(?:public\s+static\s+\w+\s+fromValue\s*\(\s*String\s+\w*\s*\))")

_FROM_STRING = re.compile(r"(?:public\s+static\s+\w+\s+fromString\s*\(\s*String\s+\w*\s*\))")


# 查找repo 根目录。
def _find_repo_root() -> Path:
    """返回：
    解析后的 HookContext；失败时携带 parse_error。
    """
    script = Path(__file__).resolve()
    # 返回 script.parent.parent.parent 的计算结果。
    return script.parent.parent.parent


# 维护扫描 文件。
def _scan_file(file_path: Path) -> EnumInfo | None:
    """参数：
        file_path: 待检查的路径。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
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


# 维护扫描 全部。
def scan_all(repo_root: Path) -> list[EnumInfo]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    results: list[EnumInfo] = []
    for module in SCAN_MODULES:
        module_dir = repo_root / module
        if not module_dir.exists():
            continue
        for java_file in sorted(module_dir.rglob("*.java")):
            info = _scan_file(java_file)
            if info is not None:
                results.append(info)
    return results


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


# 判断是否external。
def _is_external(enum_info: EnumInfo) -> bool:
    """参数：
        enum_info: enum info 参数。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    simple_name = enum_info.fqn.rsplit(".", 1)[-1]
    return simple_name not in INTERNAL_ENUMS


# 维护报告。
def report(enums: list[EnumInfo]) -> tuple[list[EnumInfo], list[EnumInfo]]:
    """参数：
        enums: enums 参数。

    返回：
        结果 tuple。
    """
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


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
    进程退出码。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    for i, arg in enumerate(sys.argv):
        if arg == '--changed-files' and i + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[i + 1])
            break
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

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
