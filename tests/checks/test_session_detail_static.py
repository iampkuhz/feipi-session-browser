"""验证 Session Detail 静态检查的关键成功与失败分支。"""

from pathlib import Path

import pytest
from scripts.checks.web import check_session_detail_static as static_check

REPO_ROOT = Path(__file__).resolve().parents[2]

GOOD_CSS = """
body.hide-left .shell.phase1-shell { grid-template-columns: 0 minmax(0, 1fr); }
.shell.phase1-shell .main { grid-column: 1 / -1; width: 100%; min-width: 0; }
.session-detail-phase1 { width: min(100%, 1360px); margin: 0 auto; }
.hero-main { grid-template-columns: 1fr; }
.hero-title { overflow-wrap: break-word; word-break: normal; }
"""
GOOD_BASE = '<div class="shell{% block shell_class %}{% endblock %}" data-session-detail-shell>'
GOOD_SESSION = """
{% extends "base.html" %}
{% block shell_class %} no-inspector phase1-shell{% endblock %}
"""


def _run_fixture(
    tmp_path: Path, *, css: str = GOOD_CSS, base: str = GOOD_BASE, session: str = GOOD_SESSION
) -> dict:
    """写入最小静态资源，并调用唯一检查实现。"""
    css_path = tmp_path / 'shell.css'
    base_path = tmp_path / 'base.html'
    session_path = tmp_path / 'session.html'
    css_path.write_text(css, encoding='utf-8')
    base_path.write_text(base, encoding='utf-8')
    session_path.write_text(session, encoding='utf-8')
    return static_check._run_checks(css_path, base_path, session_path, None)  # noqa: SLF001


def _failure_codes(result: dict) -> set[str]:
    """只提取稳定错误码，避免测试绑定诊断文案。"""
    return {failure['code'] for failure in result['failures']}


@pytest.mark.contract_case('UI-SD-016')
def test_complete_static_contract_passes(tmp_path: Path) -> None:
    result = _run_fixture(tmp_path)

    assert result['status'] == 'PASS'
    assert result['failures'] == []


@pytest.mark.contract_case('UI-SD-016')
@pytest.mark.parametrize(
    ('css', 'expected_code'),
    [
        (
            '.shell.phase1-shell .main { grid-column: 1 / -1; }',
            'MISSING_PHASE1_HIDE_LEFT_OVERRIDE',
        ),
        (
            'body.hide-left .shell.phase1-shell { grid-template-columns: 0 minmax(0, 1fr); }',
            'MISSING_PHASE1_MAIN_GRID_COLUMN',
        ),
        (
            GOOD_CSS.replace(
                '.hero-main { grid-template-columns: 1fr; }',
                '.session-detail-phase1 .hero-main '
                '{ grid-template-columns: minmax(0, 1fr) minmax(360px, 520px); }',
            ),
            'HERO_MAIN_STILL_TWO_COLUMN',
        ),
        (
            GOOD_CSS.replace(
                '.hero-title { overflow-wrap: break-word; word-break: normal; }',
                '.hero-title { overflow-wrap: anywhere; }',
            ),
            'HERO_TITLE_UNSAFE_ANYWHERE_WRAP',
        ),
        (
            GOOD_CSS.replace(
                '.hero-title { overflow-wrap: break-word; word-break: normal; }',
                '.hero-title { word-break: break-all; }',
            ),
            'HERO_TITLE_UNSAFE_ANYWHERE_WRAP',
        ),
    ],
)
def test_css_contract_reports_stable_failure(tmp_path: Path, css: str, expected_code: str) -> None:
    result = _run_fixture(tmp_path, css=css)

    assert result['status'] == 'FAIL'
    assert expected_code in _failure_codes(result)


@pytest.mark.contract_case('UI-SD-016')
@pytest.mark.parametrize(
    ('base', 'session', 'expected_code'),
    [
        (GOOD_BASE, '{% extends "base.html" %}', 'MISSING_SESSION_SHELL_CLASS_HOOK'),
        (
            '<div class="shell" data-session-detail-shell>',
            GOOD_SESSION,
            'MISSING_BASE_SHELL_CLASS_APPLICATION',
        ),
    ],
)
def test_template_wiring_reports_stable_failure(
    tmp_path: Path, base: str, session: str, expected_code: str
) -> None:
    result = _run_fixture(tmp_path, base=base, session=session)

    assert result['status'] == 'FAIL'
    assert expected_code in _failure_codes(result)


@pytest.mark.contract_case('UI-SD-016')
def test_repository_static_resources_pass() -> None:
    """真实资源缺失或不符合契约时必须失败，不能静默放过。"""
    result = static_check._run_checks(  # noqa: SLF001
        static_check.SHELL_CSS_FILE,
        static_check.BASE_HTML,
        static_check.SESSION_HTML,
    )

    assert result['status'] == 'PASS', result['failures']
