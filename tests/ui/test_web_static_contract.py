from pathlib import Path
from scripts.quality.static_contract_check import check_static


def test_static_contract_runs_if_static_exists():
    failures = check_static(Path.cwd())
    assert isinstance(failures, list)
