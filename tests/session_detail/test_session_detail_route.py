"""TASK: Session detail route smoke test.

Starts a real HTTP server on a test port, requests a session detail URL,
and asserts the page renders successfully (HTTP 200, key DOM elements present).
"""

import pytest


class TestSessionDetailRoute:
    """Smoke test for the session detail HTTP route."""

    @pytest.mark.contract_case('ROUTE-API-001')
    def test_session_detail_returns_200(self, local_test_server):
        """Session detail page must return HTTP 200, not 5xx."""
        base_url, agent, session_id = local_test_server
        url = f'{base_url}/sessions/{agent}/{session_id}'
        from tests.conftest import get_html

        html = get_html(url)
        assert len(html) > 100

    @pytest.mark.contract_case('ROUTE-API-001')
    def test_session_detail_contains_trace_panel(self, local_test_server):
        """Session detail page must contain the trace panel."""
        base_url, agent, session_id = local_test_server
        url = f'{base_url}/sessions/{agent}/{session_id}'
        from tests.conftest import get_html

        html = get_html(url)
        assert 'trace-panel' in html, 'Session detail must contain trace-panel'
        has_trace_list = 'data-trace-list' in html or 'sd-trace-list' in html
        assert has_trace_list, 'Session detail must contain trace list container'

    @pytest.mark.contract_case('ROUTE-API-001')
    def test_session_detail_contains_metrics(self, local_test_server):
        """Session detail page must contain the metrics strip."""
        base_url, agent, session_id = local_test_server
        url = f'{base_url}/sessions/{agent}/{session_id}'
        from tests.conftest import get_html

        html = get_html(url)
        assert 'sd-kpi' in html or 'sd-kpis' in html, 'Session detail must contain KPI metrics'

    @pytest.mark.contract_case('ROUTE-API-001')
    def test_session_detail_no_server_error(self, local_test_server):
        """Session detail page must not render the error.html template."""
        base_url, agent, session_id = local_test_server
        url = f'{base_url}/sessions/{agent}/{session_id}'
        from tests.conftest import get_html

        html = get_html(url)
        assert '<title>Error - Agent Run Profiler</title>' not in html, (
            'Session detail must not render the error page'
        )
        assert 'state-panel__icon--error' not in html, (
            'Session detail must not contain error state panel'
        )
