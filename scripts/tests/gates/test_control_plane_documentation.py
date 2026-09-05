"""Gate 控制面文档的自包含结构与图源契约。"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCUMENT = ROOT / 'docs' / 'gates' / 'gate-control-plane.md'


def _document_text() -> str:
    return DOCUMENT.read_text(encoding='utf-8')


def test_terms_are_introduced_before_commands_and_flow() -> None:
    text = _document_text()

    assert text.index('## 术语') < text.index('## 命令入口')
    assert text.index('## 命令入口') < text.index('## 架构与触发流程')


def test_one_inline_diagram_combines_flow_responsibility_and_code_ownership() -> None:
    text = _document_text()

    assert text.count('```plantuml') == 1
    assert text.count('@startuml') == 1
    assert text.count('@enduml') == 1
    assert '|= 步骤 |= 阶段职责 |= 代码归属 |' in text
    for location in (
        'cli.py',
        'catalog/ + maintenance/',
        'planning/ + execution/ + maintenance/',
        'execution/ + maintenance/',
        'planning/ + execution/',
        'execution/ + checks/',
        'evidence/ + presentation/',
    ):
        assert location in text
    diagram = text.split('```plantuml\n', 1)[1].split('\n```', 1)[0]
    assert re.findall(r'^\s*:(S\d+) [^;\n]+;\s*$', diagram, re.MULTILINE) == [
        f'S{step_id}' for step_id in range(1, 11)
    ]


def test_stall_is_documented_as_persistent_execution_failure() -> None:
    text = _document_text()

    assert '不可清除的停滞事实' in text
    assert 'FAIL reason=process-stalled' in text
    assert 'CLI 返回 2' in text
    assert 'STALL 不自动终止进程' in text


def test_internal_functions_are_contextualized_as_navigation_entries() -> None:
    text = _document_text()

    assert '## 代码导航：排查某一步时看哪里' in text
    assert '这些函数不是命令参数' in text
    for function_name in (
        'capture_change_snapshot',
        'match_trigger',
        'compile_gate_plan',
        'adapt_recipe_step',
        'supervise_process',
        'classify_owner_outcome',
        'orchestrate_gate_run',
        'store_run_receipt',
        'audit_gate_health',
    ):
        assert f'`{function_name}`' in text


def test_stage_ownership_has_no_second_document_or_external_diagram_source() -> None:
    text = _document_text()
    ignore_rules = (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()

    assert '## 阶段与文件归属' not in text
    assert '## 修改步骤' not in text
    assert '/docs/gates/diagrams/' in ignore_rules
    assert '](diagrams/' not in text
