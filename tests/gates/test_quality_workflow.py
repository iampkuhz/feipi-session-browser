"""CI 统一 Gate receipt 与 Java portability 分工合同。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_quality_workflow_uses_incremental_base_and_manual_full() -> None:
    text = (ROOT / '.github/workflows/quality.yml').read_text(encoding='utf-8')

    assert 'push:' in text
    assert 'pull_request:' in text
    assert 'workflow_dispatch:' in text
    assert 'python3 scripts/gates/cli.py run --mode incremental --base "$base"' in text
    assert 'python3 scripts/gates/cli.py run --mode full' in text
    assert 'path: tmp/quality/runs/' in text
    assert 'if-no-files-found: error' in text


def test_java_matrix_is_named_as_portability_not_unified_gate() -> None:
    text = (ROOT / '.github/workflows/java-quality.yml').read_text(encoding='utf-8')

    assert 'name: Java Portability' in text
    assert 'java-portability:' in text
    assert '统一 Gate receipt 由 quality.yml 负责' in text
