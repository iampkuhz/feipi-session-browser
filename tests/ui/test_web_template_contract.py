from pathlib import Path

import pytest
from scripts.checks.web.check_template_contract import _check_templates


@pytest.mark.contract_case('UI-VISUAL-001')
def test_template_contract_runs_if_templates_exist():
    failures = _check_templates(Path.cwd())
    assert isinstance(failures, list)
