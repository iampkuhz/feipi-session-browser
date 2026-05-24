from pathlib import Path
from scripts.quality.static_contract_check import check_static


def test_static_contract_runs_if_static_exists():
    errors, warnings = check_static(Path.cwd())
    assert isinstance(errors, list)
    assert isinstance(warnings, list)
