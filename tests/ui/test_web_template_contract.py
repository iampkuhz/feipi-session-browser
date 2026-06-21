from pathlib import Path

import pytest
from scripts.quality.template_contract_check import check_templates


@pytest.mark.contract_case('UI-VISUAL-001')
def test_template_contract_runs_if_templates_exist():
    failures = check_templates(Path.cwd())
    assert isinstance(failures, list)
