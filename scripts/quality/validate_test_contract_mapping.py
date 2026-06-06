#!/usr/bin/env python3
"""测试契约映射校验脚本。

扫描 tests/acceptance/features/*.md 中的契约用例表，
与 tests/**/*.py（pytest marker）和 tests/playwright/**/*.js|ts
（Playwright test 标题）进行交叉校验，生成覆盖率报告和孤立测试报告。

退出码：0 = PASS，1 = FAIL
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 正则表达式
# ---------------------------------------------------------------------------

# MD 契约用例行（9 列）
# 列序：用例ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置
_MD_ROW_RE = re.compile(
    r'\|\s*'
    r'(\w[\w-]*\d+)\s*\|\s*'        # 1: 用例 ID
    r'(P[0-3])\s*\|\s*'             # 2: 优先级
    r'(\w+)\s*\|\s*'                # 3: 分层
    r'(.*?)\s*\|\s*'                # 4: 场景
    r'(.*?)\s*\|\s*'                # 5: 怎么测
    r'(.*?)\s*\|\s*'                # 6: 必须断言
    r'([^|]+?)\s*\|\s*'                # 7: 测试类型
    r'([^|]+?)\s*\|\s*'                # 8: 关联检查
    r'([^|]+?)\s*\|'                   # 9: 代码位置
)

# pytest marker
# @pytest.mark.contract_case("ID-1", "ID-2")
# pytestmark = pytest.mark.contract_case("ID-1", "ID-2")
_PYTEST_MARKER_RE = re.compile(
    r'^\s*(?:@pytest\.mark\.contract_case|pytestmark\s*=\s*pytest\.mark\.contract_case)\((.*?)\)',
    re.MULTILINE
)
# 提取括号内引号中的 ID
_QUOTED_ID_RE = re.compile(r'["\']([\w][\w-]*\d+)["\']')

# Playwright test 标题中的契约 ID
# 匹配 [UI-XXX-001] 格式（至少 3 位数字结尾）
_PLAYWRIGHT_ID_RE = re.compile(r'\[([A-Z][A-Z0-9-]*\d{3,})\]')

# Playwright test() 调用（跨行匹配标题字符串）
# 匹配 test('... 或 test("...
_PLAYWRIGHT_TEST_RE = re.compile(
    r"""(?:^|\n)\s*test\s*\(\s*"""
    r"""(['"])"""                       # 引号类型捕获组
    r"""(.*?)"""                        # 标题内容（非贪婪）
    r"""\1""",                          # 匹配闭合引号
    re.DOTALL
)

# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------


def _parse_md_features(features_dir: Path) -> dict[str, dict]:
    """从 tests/acceptance/features/*.md 解析契约用例。

    返回 {case_id: {priority, layer, scenario, how, assertions,
                     test_type, related_check, code_location, source_file}}
    """
    cases: dict[str, dict] = {}
    duplicates: list[str] = []

    for md_file in sorted(features_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            m = _MD_ROW_RE.search(line)
            if not m:
                continue
            case_id = m.group(1).strip()
            if case_id in cases:
                duplicates.append(case_id)
            cases[case_id] = {
                "priority": m.group(2).strip(),
                "layer": m.group(3).strip(),
                "scenario": m.group(4).strip(),
                "how": m.group(5).strip(),
                "assertions": m.group(6).strip(),
                "test_type": m.group(7).strip(),
                "related_check": m.group(8).strip(),
                "code_location": m.group(9).strip(),
                "source_file": str(md_file.name),
            }

    return cases, duplicates


def _parse_pytest_markers(tests_dir: Path) -> dict[str, dict]:
    """从 tests/**/*.py 提取 @pytest.mark.contract_case 标记。

    返回 {case_id: {files: [str], type: "pytest"}}
    """
    binding: dict[str, dict] = {}

    for py_file in sorted(tests_dir.rglob("*.py")):
        # 跳过 __pycache__
        if "__pycache__" in str(py_file):
            continue
        text = py_file.read_text(encoding="utf-8")
        rel = str(py_file.relative_to(tests_dir.parent))

        for m in _PYTEST_MARKER_RE.finditer(text):
            ids_in_marker = _QUOTED_ID_RE.findall(m.group(1))
            for case_id in ids_in_marker:
                case_id = case_id.strip()
                if case_id not in binding:
                    binding[case_id] = {"files": [], "type": "pytest"}
                if rel not in binding[case_id]["files"]:
                    binding[case_id]["files"].append(rel)

    return binding


def _parse_playwright_ids(tests_dir: Path) -> dict[str, dict]:
    """从 tests/playwright/**/*.js|ts 提取 test('...') 标题中的契约 ID。

    返回 {case_id: {files: [str], type: "playwright"}}
    """
    binding: dict[str, dict] = {}
    pw_dir = tests_dir / "playwright"
    if not pw_dir.is_dir():
        return binding

    for src_file in sorted(pw_dir.rglob("*")):
        if src_file.suffix not in (".js", ".ts"):
            continue
        if "__pycache__" in str(src_file):
            continue
        text = src_file.read_text(encoding="utf-8")
        rel = str(src_file.relative_to(tests_dir.parent))

        for m in _PLAYWRIGHT_TEST_RE.finditer(text):
            title = m.group(2)
            ids = _PLAYWRIGHT_ID_RE.findall(title)
            for case_id in ids:
                case_id = case_id.strip()
                if case_id not in binding:
                    binding[case_id] = {"files": [], "type": "playwright"}
                if rel not in binding[case_id]["files"]:
                    binding[case_id]["files"].append(rel)

    return binding


# ---------------------------------------------------------------------------
# 校验逻辑
# ---------------------------------------------------------------------------


def _validate(
    md_cases: dict[str, dict],
    code_bindings: dict[str, dict],
    md_duplicates: list[str],
    repo_root: Path,
) -> list[dict]:
    """执行全部校验规则，返回错误列表。"""
    errors: list[dict] = []

    md_ids = set(md_cases.keys())
    code_ids = set(code_bindings.keys())

    # 规则 1：MD 中 P0/P1 的 ID 必须在测试代码中出现
    for case_id, info in sorted(md_cases.items()):
        if info["priority"] in ("P0", "P1") and case_id not in code_ids:
            errors.append({
                "type": "missing_in_code",
                "id": case_id,
                "priority": info["priority"],
                "message": f"{case_id} ({info['priority']}) 在验收契约中定义，但未在任何测试代码中绑定",
            })

    # 规则 2：测试代码里的 ID 必须在 MD 中定义
    for case_id in sorted(code_ids - md_ids):
        files = code_bindings[case_id]["files"]
        errors.append({
            "type": "orphan_in_code",
            "id": case_id,
            "message": f"{case_id} 在测试代码中绑定（{', '.join(files)}），但未在验收契约中定义",
        })

    # 规则 3：MD 中 ID 不得重复
    for dup_id in sorted(set(md_duplicates)):
        errors.append({
            "type": "duplicate_in_md",
            "id": dup_id,
            "message": f"{dup_id} 在验收契约中重复定义（出现 {md_duplicates.count(dup_id) + 1} 次）",
        })

    # 规则 4：P0/P1 不得只有 manual（测试类型为 manual 且无代码绑定）
    for case_id, info in sorted(md_cases.items()):
        if info["priority"] in ("P0", "P1"):
            test_types = [t.strip() for t in info["test_type"].split(",")]
            if all(tt.lower() == "manual" for tt in test_types) and case_id not in code_ids:
                errors.append({
                    "type": "p0_p1_manual_only",
                    "id": case_id,
                    "priority": info["priority"],
                    "message": f"{case_id} ({info['priority']}) 测试类型仅为 manual，无自动化测试覆盖",
                })

    # 规则 5：screenshot 用例必须在"关联检查"列包含 "snapshot"
    for case_id, info in sorted(md_cases.items()):
        test_types = [t.strip() for t in info["test_type"].split(",")]
        if "screenshot" in [tt.lower() for tt in test_types]:
            related = info["related_check"].lower()
            if "snapshot" not in related:
                errors.append({
                    "type": "screenshot_missing_snapshot",
                    "id": case_id,
                    "message": f"{case_id} 测试类型含 screenshot，但关联检查列未包含 snapshot 更新条件",
                })

    # 规则 6：代码位置指向的文件必须存在
    # 从 code_location 中提取实际文件路径（忽略函数名等注释）
    _file_path_re = re.compile(r'([\w./-]+\.(?:py|js|ts|html|css|json|yaml|yml|sh))')

    for case_id, info in sorted(md_cases.items()):
        loc = info["code_location"].strip()
        if not loc or loc == "—" or loc == "待补充":
            continue
        # 尝试提取文件路径
        found_any = False
        for path_str in re.split(r'[,、]', loc):
            path_str = path_str.strip().strip("`").strip()
            if not path_str:
                continue
            m_file = _file_path_re.search(path_str)
            if m_file:
                found_any = True
                target = repo_root / m_file.group(1)
                if not target.exists():
                    errors.append({
                        "type": "missing_source_file",
                        "id": case_id,
                        "message": f"{case_id} 代码位置 {m_file.group(1)} 不存在",
                    })
        # 如果找不到任何文件路径且不是"待补充"，跳过（可能是描述性文本）

    return errors


# ---------------------------------------------------------------------------
# 输出生成
# ---------------------------------------------------------------------------


def _gen_stats(md_cases: dict, code_bindings: dict) -> dict:
    """生成统计摘要。"""
    p_counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for info in md_cases.values():
        p = info["priority"]
        if p in p_counts:
            p_counts[p] += 1

    pytest_count = sum(
        1 for v in code_bindings.values() if v["type"] == "pytest"
    )
    playwright_count = sum(
        1 for v in code_bindings.values() if v["type"] == "playwright"
    )

    return {
        "md_total": len(md_cases),
        **p_counts,
        "code_bound": len(code_bindings),
        "pytest_bound": pytest_count,
        "playwright_bound": playwright_count,
    }


def _write_json(
    md_cases: dict,
    code_bindings: dict,
    errors: list[dict],
    stats: dict,
    output: Path,
) -> None:
    """写入 JSON 映射数据。"""
    data = {
        "cases_from_md": md_cases,
        "cases_from_code": code_bindings,
        "validation_errors": errors,
        "stats": stats,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_coverage_report(
    md_cases: dict,
    code_bindings: dict,
    output: Path,
) -> None:
    """生成 TEST_CONTRACT_COVERAGE.md。"""
    # 按领域（来源文件前缀）分组
    groups: dict[str, list[tuple[str, dict]]] = {}
    for case_id, info in sorted(md_cases.items()):
        prefix = info["source_file"].replace(".md", "")
        groups.setdefault(prefix, []).append((case_id, info))

    lines = [
        "# 测试契约覆盖率报告",
        "",
        "> 由 `scripts/quality/validate_test_contract_mapping.py` 自动生成。",
        "",
    ]

    total = len(md_cases)
    bound = 0
    for case_id in md_cases:
        if case_id in code_bindings:
            bound += 1

    lines.append(f"**总体覆盖率**: {bound}/{total} ({bound*100//total if total else 0}%)")
    lines.append("")

    for group_name, items in sorted(groups.items()):
        lines.append(f"## {group_name}")
        lines.append("")
        lines.append("| 用例 ID | 优先级 | 分层 | 测试类型 | 代码绑定 |")
        lines.append("|---|---|---|---|---|")
        for case_id, info in items:
            code_ref = ""
            if case_id in code_bindings:
                code_ref = ", ".join(code_bindings[case_id]["files"])
            lines.append(
                f"| {case_id} | {info['priority']} | {info['layer']} "
                f"| {info['test_type']} | {code_ref} |"
            )
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def _write_orphan_report(
    md_cases: dict,
    code_bindings: dict,
    errors: list[dict],
    output: Path,
) -> None:
    """生成 ORPHAN_TESTS.md。"""
    lines = [
        "# 孤立测试报告",
        "",
        "> 由 `scripts/quality/validate_test_contract_mapping.py` 自动生成。",
        "",
    ]

    # 代码中有但 MD 中无的 ID
    md_ids = set(md_cases.keys())
    orphans_in_code = sorted(set(code_bindings.keys()) - md_ids)
    lines.append(f"## 代码中定义但未在契约中定义的 ID（{len(orphans_in_code)}）")
    lines.append("")
    if orphans_in_code:
        lines.append("| 用例 ID | 测试文件 | 测试类型 |")
        lines.append("|---|---|---|")
        for case_id in orphans_in_code:
            info = code_bindings[case_id]
            files = ", ".join(info["files"])
            lines.append(f"| {case_id} | {files} | {info['type']} |")
    else:
        lines.append("无")
    lines.append("")

    # MD 中无代码绑定的 P0/P1
    p0_p1_unbound = []
    for case_id, info in sorted(md_cases.items()):
        if info["priority"] in ("P0", "P1") and case_id not in code_bindings:
            p0_p1_unbound.append((case_id, info))

    lines.append(f"## 契约中 P0/P1 但无代码绑定的 ID（{len(p0_p1_unbound)}）")
    lines.append("")
    if p0_p1_unbound:
        lines.append("| 用例 ID | 优先级 | 分层 | 测试类型 |")
        lines.append("|---|---|---|---|")
        for case_id, info in p0_p1_unbound:
            lines.append(
                f"| {case_id} | {info['priority']} | {info['layer']} "
                f"| {info['test_type']} |"
            )
    else:
        lines.append("无")
    lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 控制台输出
# ---------------------------------------------------------------------------


def _print_console(md_cases, code_bindings, errors, stats):
    """打印控制台摘要。"""
    print("=" * 60)
    print("测试契约映射校验")
    print("=" * 60)
    print()

    # 统计
    print(f"MD 用例总数: {stats['md_total']}")
    print(f"  P0: {stats['P0']}")
    print(f"  P1: {stats['P1']}")
    print(f"  P2: {stats['P2']}")
    print(f"  P3: {stats['P3']}")
    print()
    print(f"代码绑定总数: {stats['code_bound']}")
    print(f"  pytest: {stats['pytest_bound']}")
    print(f"  playwright: {stats['playwright_bound']}")
    print()

    # 校验结果
    if not errors:
        print("校验结果: 全部通过")
    else:
        print(f"校验问题 ({len(errors)} 项):")
        print("-" * 60)
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] [{err['type']}] {err['message']}")
        print("-" * 60)

    print()
    status = "PASS" if not errors else "FAIL"
    print(f"状态: {status}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="测试契约映射校验：检查验收契约与测试代码的一致性"
    )
    parser.add_argument(
        "--change-id",
        default=None,
        help="变更 ID（可选，用于日志隔离）",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="仓库根目录（默认为脚本所在仓库的根）",
    )
    args = parser.parse_args()

    # 确定仓库根目录
    if args.repo_root:
        repo_root = Path(args.repo_root).resolve()
    else:
        # 默认脚本在 scripts/quality/，向上两级
        repo_root = Path(__file__).resolve().parent.parent.parent
        repo_root = repo_root.resolve()

    features_dir = repo_root / "tests" / "acceptance" / "features"
    tests_dir = repo_root / "tests"
    generated_dir = repo_root / "tests" / "acceptance" / "generated"
    tmp_dir = repo_root / "tmp" / "acceptance"

    # 检查 features 目录
    if not features_dir.is_dir():
        print(f"错误: 验收契约目录不存在: {features_dir}", file=sys.stderr)
        return 1

    # 创建输出目录
    generated_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 1. 解析 MD 契约
    md_cases, md_duplicates = _parse_md_features(features_dir)
    print(f"解析验收契约: {len(md_cases)} 个用例 (来自 {len(set(c['source_file'] for c in md_cases.values()))} 个文件)")

    # 2. 解析 pytest markers
    pytest_bindings = _parse_pytest_markers(tests_dir)
    print(f"解析 pytest marker: {len(pytest_bindings)} 个用例 ID")

    # 3. 解析 Playwright IDs
    playwright_bindings = _parse_playwright_ids(tests_dir)
    print(f"解析 Playwright ID: {len(playwright_bindings)} 个用例 ID")

    # 4. 合并代码绑定
    code_bindings: dict[str, dict] = {}
    for source in (pytest_bindings, playwright_bindings):
        for case_id, info in source.items():
            if case_id not in code_bindings:
                code_bindings[case_id] = {
                    "files": list(info["files"]),
                    "type": info["type"],
                }
            else:
                # 合并文件列表
                for f in info["files"]:
                    if f not in code_bindings[case_id]["files"]:
                        code_bindings[case_id]["files"].append(f)
                # 如果已有 pytest，保持 pytest；否则用新类型
                if code_bindings[case_id]["type"] == "pytest":
                    pass  # keep pytest
                else:
                    code_bindings[case_id]["type"] = info["type"]

    # 5. 校验
    errors = _validate(md_cases, code_bindings, md_duplicates, repo_root)

    # 6. 统计
    stats = _gen_stats(md_cases, code_bindings)

    # 7. 输出
    _print_console(md_cases, code_bindings, errors, stats)

    _write_json(
        md_cases, code_bindings, errors, stats,
        tmp_dir / "test-contract-mapping.json",
    )
    print(f"JSON 映射: {tmp_dir / 'test-contract-mapping.json'}")

    _write_coverage_report(
        md_cases, code_bindings,
        generated_dir / "TEST_CONTRACT_COVERAGE.md",
    )
    print(f"覆盖率报告: {generated_dir / 'TEST_CONTRACT_COVERAGE.md'}")

    _write_orphan_report(
        md_cases, code_bindings, errors,
        generated_dir / "ORPHAN_TESTS.md",
    )
    print(f"孤立测试报告: {generated_dir / 'ORPHAN_TESTS.md'}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
