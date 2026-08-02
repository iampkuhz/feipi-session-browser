"""校验当前 42 个 Gate 的中文使用手册与 typed catalog 一致。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from scripts.gates.catalog import CATALOG, GATES
from scripts.gates.model import MinimumTier, RunKind

if TYPE_CHECKING:
    from scripts.gates.model import GateSpec

ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = ROOT / 'config' / 'gates.yaml'
GUIDE = ROOT / 'config' / 'gates' / 'README.md'
ROW = re.compile(
    r'^\| `(?P<name>[^`]+)` \| (?P<description>.*?) \| '
    r'`(?P<method>[^`]+)` \| `(?P<targets>[^`]+)` \| '
    r'`(?P<tier>[^`]+)` \| (?P<trigger>.*?) \|$'
)
FILE_MARKER = re.compile(r'^<!-- gate-file: (?P<path>gates/[a-z0-9-]+\.yaml) -->$')


def _declared_fragments() -> tuple[tuple[str, ...], dict[str, str]]:
    """返回根索引中的分片顺序，以及每个 Gate 唯一所属的分片。"""
    root = yaml.safe_load(CATALOG_ROOT.read_text(encoding='utf-8'))
    files = tuple(root['gate_files'])
    fragments: dict[str, str] = {}
    for relative in files:
        fragment = yaml.safe_load((ROOT / 'config' / relative).read_text(encoding='utf-8'))
        for gate in fragment['gates']:
            assert gate['name'] not in fragments
            fragments[gate['name']] = relative
    return files, fragments


def _documented_rows() -> list[dict[str, str]]:
    """解析标记区内的 Gate 表格，并保留每行当前所属的分片。"""
    text = GUIDE.read_text(encoding='utf-8')
    body = text.split('<!-- GATE-CATALOG:START -->', 1)[1].split('<!-- GATE-CATALOG:END -->', 1)[0]
    fragment = ''
    rows: list[dict[str, str]] = []
    for line in body.splitlines():
        if match := FILE_MARKER.fullmatch(line):
            fragment = match['path']
        elif match := ROW.fullmatch(line):
            rows.append({**match.groupdict(), 'fragment': fragment})
    return rows


def _execution_method(gate: GateSpec) -> str:
    """从唯一 run 声明派生手册中的合并执行方式。"""
    run = gate.run
    if run.kind is RunKind.JAVA_RULE:
        return f'Java Rule · {",".join(run.java_rules)}'
    if run.kind is RunKind.GRADLE_TASK:
        return f'Gradle Task · {",".join(run.tasks)}'
    if run.kind is RunKind.PYTHON_CHECK:
        return f'Python Check · {run.check}'
    if run.kind is RunKind.PLAYWRIGHT:
        return 'Playwright · configured suite'
    if run.kind is RunKind.SCAN_SMOKE:
        return 'Scan Smoke · configured suite'

    argv = run.argv
    if '-m' in argv:
        index = argv.index('-m')
        module = argv[index + 1]
        if module == 'pytest':
            return 'Command · pytest (harness tests)'
        suffix = f' {argv[index + 2]}' if module == 'ruff' else ''
        return f'Command · {module}{suffix}'
    if argv[0] == 'bash':
        return 'Command · bash -n' if argv[1] == '-n' else f'Command · {argv[1]}'
    if argv[0].startswith('{'):
        return f'Command · {argv[1]}'
    return f'Command · {argv[0]}'


def test_gate_guide_covers_current_catalog_once() -> None:
    """目录恰好覆盖当前 42 个 Gate，且每个名称只出现一行。"""
    rows = _documented_rows()
    names = [row['name'] for row in rows]
    expected_names = {gate.name for gate in GATES}

    assert len(rows) == len(GATES) == 42
    assert len(names) == len(set(names))
    assert set(names) == expected_names

    text = GUIDE.read_text(encoding='utf-8')
    assert '**42 个逻辑 Gate**' in text


def test_gate_guide_matches_fragments_and_typed_run_taxonomy() -> None:
    """分片、说明、Target、Tier 与合并执行方式均从 catalog 派生。"""
    files, fragments = _declared_fragments()
    by_name = {gate.name: gate for gate in GATES}
    rows = _documented_rows()
    text = GUIDE.read_text(encoding='utf-8')

    assert {row['fragment'] for row in rows} == set(files)
    for relative in files:
        assert f']({Path(relative).name})' in text

    for row in rows:
        gate = by_name[row['name']]
        assert row['fragment'] == fragments[gate.name]
        assert row['description'] == gate.description
        assert row['method'] == _execution_method(gate)
        assert row['targets'] == '、'.join(gate.targets)
        assert row['tier'] == gate.minimum_tier.value

    assert {row['method'].split(' · ', 1)[0] for row in rows} == {
        'Command',
        'Python Check',
        'Playwright',
        'Scan Smoke',
        'Gradle Task',
        'Java Rule',
    }
    assert '| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |' in text
    assert '| Gate | 作用 | 实现入口 | 执行通道 |' not in text


def test_gate_guide_trigger_examples_are_real_target_patterns() -> None:
    """触发摘要只引用真实 target pattern；空 pattern 使用唯一明确短语。"""
    by_name = {gate.name: gate for gate in GATES}
    for row in _documented_rows():
        gate = by_name[row['name']]
        examples = re.findall(r'`([^`]+)`', row['trigger'])
        if not examples:
            assert row['trigger'] == 'Target 命中即运行'
            assert all(not rule.patterns for rule in gate.target_rules)
            continue
        assert 1 <= len(examples) <= 3
        assert set(examples) <= set(gate.patterns)


def test_gate_guide_explains_targets_and_file_to_gate_flow() -> None:
    """8 个 Target、两层匹配和 full-only 说明均与 catalog 一致。"""
    text = GUIDE.read_text(encoding='utf-8')
    required_candidates = [gate for gate in GATES if gate.minimum_tier is not MinimumTier.FULL]
    target_section = text.split('## 8 个 Target 的完整目录', 1)[1].split(
        '## 从一个改动文件到真正执行的 Gate', 1
    )[0]
    documented_target_counts = {
        match.group(1): int(match.group(2))
        for match in re.finditer(r'^\| `([^`]+)` \|.*\| (\d+) \|$', target_section, re.MULTILINE)
    }
    expected_target_counts = {
        target.name: sum(target.name in gate.targets for gate in GATES)
        for target in CATALOG.targets
    }

    assert len(required_candidates) == 40
    assert len(CATALOG.targets) == 8
    assert documented_target_counts == expected_target_counts
    assert '**40 个可进入 `required`**' in text
    assert '**8 个 target**' in text
    assert '`pythonDependencyVulnerabilities` 和 `javaApiSnapshot` 是仅限 `full`' in text
    assert '根 YAML 的 pattern 做“文件 → target”' in text
    assert '分片 YAML 的 pattern 做\n“target + 文件 → Gate”' in text
    assert '`scripts/gates/cli.py::get_changed_files`' in text
    assert '`path_rules[].patterns`' in text
    assert '`docs/acceptance-cases/features/HOOK_HARNESS.md`' in text


def test_gate_guide_explains_schema_and_all_six_execution_methods() -> None:
    """手册先解释字段、取值和合并执行方式，再给完整目录。"""
    text = GUIDE.read_text(encoding='utf-8')
    catalog_section = text.split('<!-- GATE-CATALOG:START -->', 1)[0]
    for term in (
        'gate_defaults',
        'targets',
        'gate_files',
        'path_rules',
        'target_triggers',
        'order',
        'patterns',
        'run',
    ):
        assert f'`{term}`' in catalog_section
    for method in (
        'Command · ...',
        'Python Check · <check-id>',
        'Playwright · configured suite',
        'Scan Smoke · configured suite',
        'Gradle Task · <task>',
        'Java Rule · <rule-id>',
    ):
        assert f'`{method}`' in catalog_section
    assert '根索引没有 `version`' in text
    assert '“仓库维护清单”' in text
    assert '`forbidden_root_paths` 不是“所有生成文件”' in text


def test_gate_maintenance_docs_link_current_guide_without_catalog_versions() -> None:
    """维护入口统一链接当前手册，不再指导维护 Catalog 版本。"""
    documents = {
        ROOT / 'scripts' / 'gates' / 'README.md': '../../config/gates/README.md',
        ROOT / 'scripts' / 'README.md': '../config/gates/README.md',
        ROOT / 'harness' / 'README.md': '../config/gates/README.md',
        ROOT / 'docs' / 'agent-runtime.md': '../config/gates/README.md',
    }
    for path, link in documents.items():
        content = path.read_text(encoding='utf-8')
        assert f']({link})' in content
        assert not re.search(r'(?i)gate[- ]catalog\s*[: ]?v\d+', content)


def test_gate_descriptions_explain_business_purpose() -> None:
    """禁止重新使用“执行 Gate 名称所定义检查”这类无信息模板。"""
    for gate in GATES:
        assert f'执行 {gate.name} 所定义' not in gate.description
        assert len(gate.description) >= 12
