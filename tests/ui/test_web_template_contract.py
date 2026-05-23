from pathlib import Path
from scripts.quality.template_contract_check import check_templates


def test_template_contract_runs_if_templates_exist():
    failures = check_templates(Path.cwd())
    assert isinstance(failures, list)
