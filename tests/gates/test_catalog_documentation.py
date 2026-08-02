"""校验 45 个 Gate 的中文精简目录与机器 catalog 一致。"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from scripts.gates.catalog import GATES

if TYPE_CHECKING:
    from scripts.gates.model import GateSpec

ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = ROOT / 'config' / 'gates.yaml'
GUIDE = ROOT / 'config' / 'gates' / 'README.md'
ROW = re.compile(
    r'^\| `(?P<name>[^`]+)` \| (?P<description>.*?) \| '
    r'`(?P<owner>[^`]+)` \| `(?P<targets>[^`]+)` \| (?P<trigger>.*?) \|$'
)
FILE_MARKER = re.compile(r'^<!-- gate-file: (?P<path>gates/[a-z0-9-]+\.yaml) -->$')


def _declared_fragments() -> tuple[tuple[str, ...], dict[str, str]]:
    """返回根索引中的分片顺序，以及每个 Gate 唯一所属的分片。"""
    root = yaml.safe_load(CATALOG_ROOT.read_text(encoding='utf-8'))
    files = tuple(root['gate_files'])
    owners: dict[str, str] = {}
    for relative in files:
        fragment = yaml.safe_load((ROOT / 'config' / relative).read_text(encoding='utf-8'))
        for gate in fragment['gates']:
            assert gate['name'] not in owners
            owners[gate['name']] = relative
    return files, owners


def _documented_rows() -> list[dict[str, str]]:
    """解析标记区内的 Gate 表格，并保留每行当前所属的分片。"""
    text = GUIDE.read_text(encoding='utf-8')
    body = text.split('<!-- GATE-CATALOG:START -->', 1)[1].split('<!-- GATE-CATALOG:END -->', 1)[0]
    fragment = ''
    rows: list[dict[str, str]] = []
    for line in body.splitlines():
        if match := FILE_MARKER.fullmatch(line):
            fragment = match['path']
            continue
        if match := ROW.fullmatch(line):
            rows.append({**match.groupdict(), 'fragment': fragment})
    return rows


def _owner(gate: GateSpec) -> str:
    """从执行声明派生 README 使用的四类精简入口。"""
    if gate.java_rules:
        return f'java:{",".join(gate.java_rules)}'
    if gate.gradle_tasks:
        tasks = ','.join(task.lstrip(':') for task in gate.gradle_tasks)
        return f'gradle:{tasks}'

    command = gate.command
    assert command is not None
    candidates = [command.argv, *(item.argv for item in command.target_argv)]
    for argv in candidates:
        if 'scripts.checks' in argv:
            index = argv.index('scripts.checks')
            return f'check:{argv[index + 1]}'
    if command.capability == 'playwright':
        return f'command:{command.capability}'

    argv = next(item for item in candidates if item)
    if '-m' in argv:
        index = argv.index('-m')
        module = argv[index + 1]
        suffix = f' {argv[index + 2]}' if module in {'ruff', 'radon'} else ''
        return f'command:{module.rsplit(".", 1)[-1]}{suffix}'
    if argv[0] == 'bash':
        command_name = 'bash -n' if argv[1] == '-n' else Path(argv[1]).name
        return f'command:{command_name}'
    if argv[0].startswith('{') and len(argv) > 1:
        return f'command:{Path(argv[1]).name}'
    return f'command:{Path(argv[0]).name}'


def test_gate_guide_covers_every_catalog_gate_once() -> None:
    """精简目录必须准确覆盖 45 个逻辑 Gate，不能遗漏或重复。"""
    rows = _documented_rows()
    names = [row['name'] for row in rows]
    assert len(rows) == 45
    assert len(names) == len(set(names))
    assert set(names) == {gate.name for gate in GATES}

    text = GUIDE.read_text(encoding='utf-8')
    assert '**45 个逻辑 Gate**' in text
    assert '44 个可进入 `required`' in text
    assert '`javaApiSnapshot` 只属于 `full`' in text


def test_gate_guide_routes_to_the_right_fragment_owner_and_target() -> None:
    """每行作用、入口、Target 和分片都必须从机器 catalog 得到证明。"""
    files, fragments = _declared_fragments()
    by_name = {gate.name: gate for gate in GATES}
    rows = _documented_rows()

    assert {row['fragment'] for row in rows} == set(files)
    for relative in files:
        assert f']({Path(relative).name})' in GUIDE.read_text(encoding='utf-8')

    for row in rows:
        gate = by_name[row['name']]
        assert row['fragment'] == fragments[gate.name]
        assert row['description'] == gate.description
        assert row['owner'] == _owner(gate)
        assert row['targets'] == '、'.join(gate.targets)

    kinds = Counter(row['owner'].split(':', 1)[0] for row in rows)
    assert kinds == {'java': 9, 'gradle': 5, 'check': 16, 'command': 15}


def test_gate_guide_trigger_examples_are_real_patterns() -> None:
    """触发摘要至少引用真实 pattern；always Gate 使用唯一明确短语。"""
    by_name = {gate.name: gate for gate in GATES}
    for row in _documented_rows():
        gate = by_name[row['name']]
        examples = re.findall(r'`([^`]+)`', row['trigger'])
        if not examples:
            assert row['trigger'] == '目标命中即运行'
            assert gate.incremental_mode.value == 'always'
            continue
        assert gate.incremental_mode.value == 'patterns'
        assert 1 <= len(examples) <= 3
        assert set(examples) <= set(gate.patterns)


def test_gate_descriptions_explain_business_purpose() -> None:
    """禁止重新使用“执行 Gate 名称所定义检查”这类无信息模板。"""
    for gate in GATES:
        assert f'执行 {gate.name} 所定义' not in gate.description
        assert len(gate.description) >= 12
