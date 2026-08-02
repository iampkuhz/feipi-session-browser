"""校验 44 个 Gate 的中文精简目录与 v6 typed catalog 一致。"""

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
    r'`(?P<implementation>[^`]+)` \| `(?P<channel>[^`]+)` \| '
    r'`(?P<targets>[^`]+)` \| `(?P<tier>[^`]+)` \| (?P<trigger>.*?) \|$'
)
FILE_MARKER = re.compile(r'^<!-- gate-file: (?P<path>gates/[a-z0-9-]+\.yaml) -->$')
OLD_GATE_NAMES = {
    'pythonCoverage',
    'pythonAudit',
    'pythonComplexity',
    'pythonDeps',
    'pythonCompile',
    'pytest',
}


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


def _implementation(gate: GateSpec) -> str:
    """从 discriminated run 派生可追踪的实现入口。"""
    run = gate.run
    if run.kind is RunKind.JAVA_RULE:
        return f'java-rule:{",".join(run.java_rules)}'
    if run.kind is RunKind.GRADLE_TASK:
        return f'gradle-task:{",".join(run.tasks)}'
    if run.kind is RunKind.PYTHON_CHECK:
        return f'python-check:{run.check}'
    if run.kind is RunKind.PLAYWRIGHT:
        return 'suite:playwright'
    if run.kind is RunKind.SCAN_SMOKE:
        return 'suite:scan-script-smoke'

    argv = run.argv
    if '-m' in argv:
        index = argv.index('-m')
        module = argv[index + 1]
        if module == 'pytest':
            return (
                'suite:session-detail-static-tests'
                if gate.name == 'sessionDetailStaticTests'
                else 'suite:python-harness-tests'
            )
        suffix = f' {argv[index + 2]}' if module == 'ruff' else ''
        return f'tool:{module}{suffix}'
    if argv[0] == 'bash':
        return 'tool:bash -n' if argv[1] == '-n' else f'tool:{argv[1]}'
    if argv[0].startswith('{'):
        return f'tool:{argv[1]}'
    return f'tool:{argv[0]}'


def _channel(gate: GateSpec) -> str:
    """执行通道只区分聚合 Gradle 与 bounded process。"""
    if gate.run.kind in {RunKind.JAVA_RULE, RunKind.GRADLE_TASK}:
        return 'gradle'
    return 'process'


def test_gate_guide_covers_v6_catalog_and_retired_names() -> None:
    """目录恰好覆盖 v6 的 44 Gate，新名完整且六个旧名零出现。"""
    rows = _documented_rows()
    names = [row['name'] for row in rows]
    expected_names = {gate.name for gate in GATES}

    assert CATALOG.version == 'gate-catalog:v6'
    assert len(rows) == len(GATES) == 44
    assert len(names) == len(set(names))
    assert set(names) == expected_names
    assert OLD_GATE_NAMES.isdisjoint(expected_names)

    text = GUIDE.read_text(encoding='utf-8')
    assert '**44 个逻辑 Gate**' in text
    for retired in OLD_GATE_NAMES:
        assert not re.search(rf'(?<![A-Za-z0-9]){re.escape(retired)}(?![A-Za-z0-9])', text)


def test_gate_guide_matches_fragments_and_typed_run_taxonomy() -> None:
    """分片、说明、Target、Tier、实现入口与执行通道均从 catalog 派生。"""
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
        assert row['implementation'] == _implementation(gate)
        assert row['channel'] == _channel(gate)
        assert row['targets'] == '、'.join(gate.targets)
        assert row['tier'] == gate.minimum_tier.value

    assert {row['channel'] for row in rows} == {'gradle', 'process'}
    assert all(
        row['implementation'].split(':', 1)[0]
        in {'java-rule', 'gradle-task', 'python-check', 'tool', 'suite'}
        for row in rows
    )
    assert '入口 / Owner' not in text
    assert not any(row['implementation'].startswith('command:') for row in rows)


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


def test_gate_guide_explains_target_order_and_full_only_audit() -> None:
    """Target 流程和 full-only 漏洞审计由运行时 catalog 计算证明。"""
    text = GUIDE.read_text(encoding='utf-8')
    audit = next(gate for gate in GATES if gate.name == 'pythonDependencyVulnerabilities')
    required_candidates = [gate for gate in GATES if gate.minimum_tier is not MinimumTier.FULL]

    assert len(required_candidates) == 42
    assert audit.minimum_tier is MinimumTier.FULL
    assert audit.network_failure == 'blocked'
    assert '**42 个可进入 `required`**' in text
    assert '`pythonDependencyVulnerabilities` 与 `javaApiSnapshot` 仅在 `full` tier' in text
    assert (
        'changed path → path rule.targets → Gate target rule（order + pattern）→ tier 过滤 → plan'
        in text
    )
    assert 'target 不是 owner、executor、tier 或 Gate 的唯一分类' in text
    assert '`acceptance-contracts` 与\n`python-standard`' in text
    assert '`session-detail`、`acceptance-contracts` 与 `python-standard`' in text


def test_gate_maintenance_docs_link_root_and_describe_v6_recipe() -> None:
    """维护入口统一链接精简目录，并使用 v6 run/defaults/strict schema recipe。"""
    documents = {
        ROOT / 'scripts' / 'gates' / 'README.md': '../../config/gates/README.md',
        ROOT / 'scripts' / 'README.md': '../config/gates/README.md',
        ROOT / 'harness' / 'README.md': '../config/gates/README.md',
        ROOT / 'docs' / 'agent-runtime.md': '../config/gates/README.md',
    }
    for path, link in documents.items():
        assert f']({link})' in path.read_text(encoding='utf-8')

    guide = GUIDE.read_text(encoding='utf-8')
    service = (ROOT / 'scripts' / 'gates' / 'README.md').read_text(encoding='utf-8')
    for term in ('gate_defaults', 'targets', 'order', 'patterns', 'run'):
        assert f'`{term}`' in guide
    assert 'exact-key/exact-type' in guide
    assert '`gradle` 和 `process`' in service
    assert 'v6 schema 未声明的兼容字段' in service


def test_gate_descriptions_explain_business_purpose() -> None:
    """禁止重新使用“执行 Gate 名称所定义检查”这类无信息模板。"""
    for gate in GATES:
        assert f'执行 {gate.name} 所定义' not in gate.description
        assert len(gate.description) >= 12
