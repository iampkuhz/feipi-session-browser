"""校验当前 41 个 Gate 的中文使用手册与双模式 typed catalog 一致。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from scripts.gates.catalog import CATALOG, GATES
from scripts.gates.model import RunKind, TriggerMode

if TYPE_CHECKING:
    from scripts.gates.model import GateSpec, RunProfile

ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = ROOT / 'config' / 'gates.yaml'
GUIDE = ROOT / 'config' / 'gates' / 'README.md'
ROW = re.compile(
    r'^\| `(?P<name>[^`]+)` \| (?P<description>.*?) \| '
    r'`(?P<method>[^`]+)` \| `(?P<targets>[^`]+)` \| '
    r'(?P<trigger>.*?) \| `(?P<incremental>[^`]+)` \| `(?P<full>[^`]+)` \|$'
)
FILE_MARKER = re.compile(r'^<!-- gate-file: (?P<path>gates/[a-z0-9-]+\.yaml) -->$')


def _declared_fragments() -> tuple[tuple[str, ...], dict[str, str]]:
    """返回根索引中的分片顺序，以及每个 Gate 唯一所属分片。"""
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
    """解析标记区内的 Gate 表格，并保留每行所属分片。"""
    body = GUIDE.read_text(encoding='utf-8').split('<!-- GATE-CATALOG:START -->', 1)[1]
    body = body.split('<!-- GATE-CATALOG:END -->', 1)[0]
    fragment = ''
    rows: list[dict[str, str]] = []
    for line in body.splitlines():
        if match := FILE_MARKER.fullmatch(line):
            fragment = match['path']
        elif match := ROW.fullmatch(line):
            rows.append({**match.groupdict(), 'fragment': fragment})
    return rows


def _execution_method(gate: GateSpec) -> str:
    """从 incremental profile 的唯一 typed run 派生合并执行方式。"""
    run = gate.run
    profile = run.incremental
    if run.kind is RunKind.JAVA_RULE:
        return f'Java Rule · {",".join(profile.rules)}'
    if run.kind is RunKind.GRADLE_TASK:
        return f'Gradle Task · {",".join(profile.tasks)}'
    if run.kind is RunKind.PYTHON_CHECK:
        return f'Python Check · {profile.check_id}'
    if run.kind is RunKind.PLAYWRIGHT:
        return 'Playwright · configured suite'
    if run.kind is RunKind.SCAN_SMOKE:
        return 'Scan Smoke · configured suite'

    argv = profile.argv
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


def _timing(profile: RunProfile) -> str:
    """返回手册约定的“目标 / timeout”简写。"""
    return f'{profile.target_seconds}s / {profile.timeout_seconds}s'


def test_gate_guide_covers_current_catalog_once() -> None:
    """目录恰好覆盖当前 41 个 Gate，且每个名称只出现一行。"""
    rows = _documented_rows()
    names = [row['name'] for row in rows]
    assert len(rows) == len(GATES) == 41
    assert len(names) == len(set(names))
    assert set(names) == {gate.name for gate in GATES}
    assert '**41 个逻辑 Gate**' in GUIDE.read_text(encoding='utf-8')


def test_gate_guide_matches_fragments_runs_triggers_and_timing() -> None:
    """分片、说明、Target、Trigger、执行方式与双模式时效均从 catalog 派生。"""
    files, fragments = _declared_fragments()
    rows = _documented_rows()
    by_name = {gate.name: gate for gate in GATES}
    assert {row['fragment'] for row in rows} == set(files)

    for row in rows:
        gate = by_name[row['name']]
        assert row['fragment'] == fragments[gate.name]
        assert row['description'] == gate.description
        assert row['method'] == _execution_method(gate)
        assert row['targets'] == ('、'.join(gate.targets) or '无')
        assert row['incremental'] == _timing(gate.run.incremental)
        assert row['full'] == _timing(gate.run.full)
        examples = re.findall(r'`([^`]+)`', row['trigger'])
        if gate.trigger.mode is TriggerMode.ALWAYS:
            assert examples == ['always']
        else:
            assert 1 <= len(examples) <= 3
            assert set(examples) <= set(gate.trigger.paths)


def test_gate_guide_explains_gate_first_targets_schema_and_statuses() -> None:
    """手册先讲清 Gate-first、人工 Target、五字段和状态语义。"""
    text = GUIDE.read_text(encoding='utf-8')
    catalog_section = text.split('<!-- GATE-CATALOG:START -->', 1)[0]
    assert len(CATALOG.targets) == 6
    assert 'acceptance-cases' not in {target.name for target in CATALOG.targets}
    assert '**6 个 Target preset**' in catalog_section
    assert 'Target 只供人工选择，不参与自动规划' in catalog_section
    assert 'changed files → Gate.trigger → selected Gates' in catalog_section
    assert '根 `path_rules` 只为改动文件附加风险分类' in catalog_section
    for field in ('name', 'description', 'trigger', 'targets', 'run'):
        assert f'`{field}`' in catalog_section
    assert '`incremental/full`' in catalog_section
    assert '`0=PASS`、`1=BLOCKED`、`2=FAIL`' in catalog_section
    assert '`BLOCKED` | 是 | 是，确认存在阻断问题' in catalog_section
    assert '`FAIL` | 否 | 否，无法判断' in catalog_section
    assert '`docs/acceptance-cases/` 是验收用例总账，不是 Target' in catalog_section
    assert '| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |' in text


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
    """禁止重新使用没有信息的 Gate 说明模板。"""
    for gate in GATES:
        assert f'执行 {gate.name} 所定义' not in gate.description
        assert len(gate.description) >= 12
