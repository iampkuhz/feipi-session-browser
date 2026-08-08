"""校验 20 个逻辑 Gate 的中文手册与 typed declaration 一致。"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.gates.catalog import CATALOG, GATES
from scripts.gates.model import RunKind

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / 'scripts' / 'gates' / 'README.md'
ROW = re.compile(
    r'^\| `(?P<name>[^`]+)` \| (?P<description>.*?) \| '
    r'(?P<execution>.*?) \| `(?P<incremental>≤\d+s)` \| `(?P<full>≤\d+s)` \|$'
)


def _documented_rows() -> list[dict[str, str]]:
    """解析手册标记区内的 Gate 行。"""

    body = GUIDE.read_text(encoding='utf-8').split('<!-- GATE-CATALOG:START -->', 1)[1]
    body = body.split('<!-- GATE-CATALOG:END -->', 1)[0]
    return [match.groupdict() for line in body.splitlines() if (match := ROW.fullmatch(line))]


def _step_tokens(step) -> tuple[str, ...]:
    """返回手册必须能定位的 leaf 和真实 owner 标识。"""

    tokens = [step.name]
    if step.kind is RunKind.PYTHON_CHECK:
        tokens.append(step.check_id)
    elif step.kind is RunKind.GRADLE_TASK:
        tokens.extend(step.tasks)
    elif step.kind is RunKind.JAVA_RULE:
        tokens.extend(step.rules)
    elif step.kind in {RunKind.PLAYWRIGHT, RunKind.SCAN_SMOKE}:
        tokens.extend(step.tests)
        tokens.extend(step.prerequisite_tasks)
    elif '-m' in step.argv:
        index = step.argv.index('-m')
        tokens.append(step.argv[index + 1])
    elif step.argv:
        command = step.argv[1] if step.argv[0].startswith('{') else step.argv[0]
        tokens.append(command)
    return tuple(token for token in tokens if token)


def test_gate_guide_covers_current_catalog_once() -> None:
    rows = _documented_rows()
    names = [row['name'] for row in rows]
    assert len(rows) == len(GATES) == 20
    assert len(names) == len(set(names))
    assert set(names) == {gate.name for gate in GATES}
    assert '**20 个逻辑 Gate**' in GUIDE.read_text(encoding='utf-8')


def test_each_row_explains_automatic_manual_and_real_execution() -> None:
    rows = {row['name']: row for row in _documented_rows()}
    for gate in GATES:
        row = rows[gate.name]
        execution = row['execution']
        assert row['description'] == gate.description
        assert '自动：' in execution
        assert f'--gate {gate.name}' in execution
        assert '执行：' in execution
        for target in gate.targets:
            assert target in execution
        if not gate.targets:
            assert '不属于 Target' in execution
        assert row['incremental'] == f'≤{gate.run.target_seconds.incremental}s'
        assert row['full'] == f'≤{gate.run.target_seconds.full}s'
        for step in gate.run.steps:
            for token in _step_tokens(step):
                assert token.lower() in execution.lower(), (gate.name, token)


def test_guide_explains_selection_health_status_and_non_blocking_targets() -> None:
    text = GUIDE.read_text(encoding='utf-8')
    introduction = text.split('<!-- GATE-CATALOG:START -->', 1)[0]
    assert len(CATALOG.targets) == 6
    assert '## 6 个 Target' in introduction
    assert '## 6 种 leaf 执行类型' in introduction
    assert all(f'`{kind.value}`' in introduction for kind in RunKind)
    assert '`system`' in introduction and '`dev`' in introduction
    assert '**自动增量：**' in introduction
    assert '**人工单项：**' in introduction
    assert '**人工分组：**' in introduction
    assert '**全量：**' in introduction
    assert (
        '同一个\n   Gate 不因 incremental/full、`--gate` 或 `--target` 改用另一套命令'
        in introduction
    )
    assert '不是 timeout' in introduction
    assert '不会因为超过数字\n被 kill' in introduction
    assert '| Gate | 作用 | 如何触发和执行 | 增量 ≤ | 全量 ≤ |' in text
    assert '`0=PASS`、`1=BLOCKED`、`2=FAIL`' in text
    assert not (ROOT / 'config' / 'gates.yaml').exists()
    assert not (ROOT / 'config' / 'gates').exists()


def test_standard_gate_exposes_six_leaf_diagnostics() -> None:
    row = {item['name']: item for item in _documented_rows()}['scriptSourceStandard']
    for leaf in (
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    ):
        assert leaf in row['execution']
    assert 'Ruff lint/import' in row['execution']
    assert 'deptry' in row['execution']
    assert 'Bandit' in row['execution']
    assert 'Vulture' in row['execution']


def test_maintenance_docs_use_one_gate_guide_and_no_yaml_catalog() -> None:
    documents = (
        ROOT / 'scripts' / 'README.md',
        ROOT / 'harness' / 'README.md',
        ROOT / 'docs' / 'agent-runtime.md',
        ROOT / 'scripts' / 'gates' / 'checks' / 'README.md',
    )
    for path in documents:
        content = path.read_text(encoding='utf-8')
        assert 'scripts/gates/README.md' in content
        assert '外部 YAML Catalog' not in content


def test_gate_descriptions_explain_business_purpose() -> None:
    for gate in GATES:
        assert f'执行 {gate.name} 所定义' not in gate.description
        assert len(gate.description) >= 12
