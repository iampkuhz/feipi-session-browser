"""Session detail LLM attribution modal contract tests.

Verifies:
1. Template renders the correct payload-kind attribute for each attribution type.
2. Attribution modal content is structured with topgrid metadata + full-width main content.
3. No "(No rendered content)" or "(No raw content)" fallbacks for attribution payloads.
4. Response attribution modal has response-specific sections.
5. Error modal has correct diagnostic structure.
6. Multiple attribution payloads render independently in the same payload_sources list.
"""

from pathlib import Path

import pytest

from session_browser.web.template_env import env

pytestmark = pytest.mark.contract_case('UI-SD-020')


def _render_payload_sources(payload_sources):
    macro = env.get_template('components/session_detail_timeline.html').module
    return macro.payload_sources(payload_sources)


def _request_usage(
    *,
    provider_request_input: int = 5000,
    fresh: int | None = 2000,
    cache_read: int = 3000,
    cache_write: int | None = 500,
    coverage: float = 4500,
    unknown: int = 500,
) -> dict:
    """构造当前 request attribution 用量契约。"""
    return {
        'provider_request_input': {
            'value': provider_request_input,
            'precision': 'provider_reported',
        },
        'input_side_component_total': {
            'value': provider_request_input + (cache_write or 0),
            'precision': 'provider_reported',
        },
        'request_content_denominator': {'value': fresh, 'precision': 'estimated'},
        'fresh': {'value': fresh, 'precision': 'estimated' if fresh is not None else 'unavailable'},
        'cache_read': {'value': cache_read, 'precision': 'provider_reported'},
        'cache_write': {
            'value': cache_write,
            'precision': 'provider_reported' if cache_write is not None else 'unavailable',
        },
        'coverage': {'value': coverage, 'precision': 'heuristic'},
        'unknown': {'value': unknown, 'precision': 'residual'},
    }


class TestAttributionModalContract:
    """Verify attribution modal rendering matches the expected contract."""

    def test_request_attribution_has_correct_payload_kind(self):
        """Template should render data-payload-kind matching the payload kind."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(),
                'buckets': [],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'data-payload-kind="llm.request_attribution"' in html
        assert 'data-payload-status="available"' in html

    def test_response_attribution_has_correct_payload_kind(self):
        resp_data = {
            'kind': 'llm.response_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': {
                    'total_output': {'value': 2000, 'precision': 'provider_reported'},
                    'visible_text': {'value': 1500, 'precision': 'estimated'},
                    'tool_use': {'value': 400, 'precision': 'heuristic'},
                    'metadata': {'value': 100, 'precision': 'estimated'},
                    'coverage': {'value': 1900, 'precision': 'heuristic'},
                    'unknown': {'value': 100, 'precision': 'residual'},
                    'finish_reason': {'value': 'tool_use', 'precision': 'exact'},
                },
                'buckets': [],
                'availability_rows': [],
                'captured_output_preview': '',
                'attribution_notes': [],
            },
        }
        html = _render_payload_sources([resp_data])
        assert 'data-payload-kind="llm.response_attribution"' in html

    def test_attribution_error_has_correct_payload_kind(self):
        err_data = {
            'kind': 'llm.attribution_error',
            'data': {
                'agent': 'claude_code',
                'call_id': 'call-001',
                'round_id': '1',
                'error_type': 'ValueError',
                'message': 'test',
                'fallback': 'fallback',
            },
        }
        html = _render_payload_sources([err_data])
        assert 'data-payload-kind="llm.attribution_error"' in html

    def test_no_fallback_for_request_attribution(self):
        """Request attribution should not render the generic fallback 'No content'."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(),
                'buckets': [],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'No content' not in html
        assert 'No rendered content' not in html
        assert 'No raw content' not in html

    def test_topgrid_metadata_present_without_left_rail(self):
        """Attribution modal should place metadata in topgrid, not a left rail."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(),
                'buckets': [],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'class="sd-attribution-topgrid"' in html
        assert 'class="sd-attribution-rail"' not in html
        assert '摘要' in html

    def test_right_main_area_present(self):
        """Attribution modal should have a right main area."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(),
                'buckets': [],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'class="sd-attribution-canvas"' in html

    def test_request_modal_has_request_specific_sections(self):
        """Request attribution should have topgrid request summary."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(),
                'buckets': [],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert '请求摘要' in html
        assert '用量分布' not in html

    def test_request_summary_merges_coverage_fields(self):
        """Coverage and residual metadata should live in the request summary card."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(coverage=0.9),
                'coverage': {
                    'provider_request_input': 5000,
                    'input_side_component_total': 5500,
                    'request_content_denominator': 2000,
                    'reconstructed_total': 4500,
                    'coverage_ratio': 0.9,
                    'residual_tokens': 500,
                    'residual_likely_sources': [],
                },
                'buckets': [],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'Provider 请求输入' in html
        assert '本地重建' in html
        assert '残差' in html
        assert '覆盖率与不确定性' not in html
        assert '可能来源' not in html

    def test_dynamic_modal_does_not_render_bottom_coverage_block(self):
        """Dynamic attribution JS should keep coverage fields in the top summary only."""
        js_path = (
            Path(__file__).resolve().parents[1]
            / 'src/session_browser/web/static/js/session-detail/attribution.js'
        )
        js = js_path.read_text(encoding='utf-8')
        assert 'Provider 请求输入' in js
        assert '本地重建' in js
        assert '未定位' in js
        assert '覆盖率与不确定性' not in js
        assert 'sd-attribution-coverage-sources' not in js
        assert '可能来源：' not in js

    def test_dynamic_modal_fetches_attribution_api(self):
        """Clicking attribution actions should render from the backend API response."""
        js_path = (
            Path(__file__).resolve().parents[1]
            / 'src/session_browser/web/static/js/session-detail/attribution.js'
        )
        js = js_path.read_text(encoding='utf-8')
        assert 'attributionApiUrl(button, apiKind)' in js
        assert '"/api/sessions/"' in js
        assert 'fetch(url, { headers: { "Accept": "application/json" } })' in js
        assert 'renderAttributionSuccess(body, payload, kind, url)' in js

    def test_trace_attribution_buttons_open_analysis_modal_before_payload_fallback(self):
        """Trace request/response attribution buttons keep the attribution analysis path."""
        js_path = (
            Path(__file__).resolve().parents[1]
            / 'src/session_browser/web/static/js/session-detail/payload.js'
        )
        js = js_path.read_text(encoding='utf-8')
        open_payload = js[js.index('function openPayload(button)') :]
        assert 'openAttributionModal(button)' in open_payload
        assert 'openPayloadContent(button)' in open_payload
        assert open_payload.index('openAttributionModal(button)') < open_payload.index(
            'openPayloadContent(button)'
        )
        assert 'directPayloadTargetForAttribution' not in js
        assert 'payloadId.replace(/-request-attribution$/, "-context")' not in js
        assert 'payloadId.replace(/-response-attribution$/, "-output")' not in js

    def test_response_modal_has_response_specific_sections(self):
        """Response attribution should have topgrid response summary."""
        resp_data = {
            'kind': 'llm.response_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': {
                    'total_output': {'value': 2000, 'precision': 'provider_reported'},
                    'visible_text': {'value': 1500, 'precision': 'estimated'},
                    'tool_use': {'value': 400, 'precision': 'heuristic'},
                    'metadata': {'value': 100, 'precision': 'estimated'},
                    'coverage': {'value': 1900, 'precision': 'heuristic'},
                    'unknown': {'value': 100, 'precision': 'residual'},
                    'finish_reason': {'value': 'tool_use', 'precision': 'exact'},
                },
                'buckets': [],
                'availability_rows': [],
                'captured_output_preview': '',
                'attribution_notes': [],
            },
        }
        html = _render_payload_sources([resp_data])
        assert '响应摘要' in html

    def test_error_modal_has_diagnostic_header(self):
        """Error modal should have '归因诊断' header."""
        err_data = {
            'kind': 'llm.attribution_error',
            'data': {
                'agent': 'claude_code',
                'call_id': 'call-001',
                'round_id': '1',
                'error_type': 'ValueError',
                'message': 'test',
                'fallback': 'fallback',
            },
        }
        html = _render_payload_sources([err_data])
        assert '归因诊断' in html
        assert '归因构建失败' in html

    def test_multiple_attribution_payloads_render_independently(self):
        """All three attribution types in same payload_sources list should render correctly."""
        payloads = [
            {
                'kind': 'llm.request_attribution',
                'payload_id': 'llm-R1-IX1-request-attribution',
                'data': {
                    'agent': 'claude_code',
                    'model': 'claude-sonnet-4',
                    'source_label': 'transcript',
                    'confidence_label': '高',
                    'request_id': 'req-1',
                    'call_id': 'call-1',
                    'usage': _request_usage(),
                    'buckets': [],
                    'availability_rows': [],
                    'captured_context_preview': '',
                    'attribution_notes': [],
                    'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
                },
            },
            {
                'kind': 'llm.response_attribution',
                'payload_id': 'llm-R1-IX1-response-attribution',
                'data': {
                    'agent': 'claude_code',
                    'model': 'claude-sonnet-4',
                    'source_label': 'transcript',
                    'confidence_label': '高',
                    'request_id': 'req-1',
                    'call_id': 'call-1',
                    'usage': {
                        'total_output': {'value': 2000, 'precision': 'provider_reported'},
                        'visible_text': {'value': 1500, 'precision': 'estimated'},
                        'tool_use': {'value': 400, 'precision': 'heuristic'},
                        'metadata': {'value': 100, 'precision': 'estimated'},
                        'coverage': {'value': 1900, 'precision': 'heuristic'},
                        'unknown': {'value': 100, 'precision': 'residual'},
                        'finish_reason': {'value': 'tool_use', 'precision': 'exact'},
                    },
                    'buckets': [],
                    'availability_rows': [],
                    'captured_output_preview': '',
                    'attribution_notes': [],
                },
            },
            {
                'kind': 'llm.attribution_error',
                'payload_id': 'llm-R1-IX2-request-attribution',
                'data': {
                    'agent': 'claude_code',
                    'call_id': 'call-2',
                    'round_id': '1',
                    'error_type': 'RuntimeError',
                    'message': 'failed',
                    'fallback': 'fallback',
                },
            },
        ]
        html = _render_payload_sources(payloads)
        # Count template occurrences - each should be rendered
        assert html.count('sd-payload-shell--attribution') >= 3
        assert '请求摘要' in html
        assert '响应摘要' in html
        assert '归因诊断' in html

    def test_precision_labels_render_correctly_in_template(self):
        """Precision tag should render the correct label in the template output."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(fresh=None, cache_write=None, coverage=3000, unknown=2000),
                'buckets': [
                    {
                        'key': 'current_user_message',
                        'label': '当前用户输入',
                        'tokens': 2000,
                        'percent': 40.0,
                        'contributes_to_total': True,
                        'precision': 'estimated',
                        'source': 'transcript',
                        'confidence_label': '中高',
                        'summary': '用户输入',
                        'content_preview': '',
                    },
                    {
                        'key': 'tool_definitions',
                        'label': '工具定义',
                        'tokens': 500,
                        'percent': 10.0,
                        'contributes_to_total': True,
                        'precision': 'heuristic',
                        'source': 'tool_list',
                        'confidence_label': '中低',
                        'summary': '工具定义估算',
                        'content_preview': '',
                    },
                ],
                'availability_rows': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
            },
        }
        html = _render_payload_sources([req_data])
        assert 'sd-precision-tag--provider_reported' in html
        assert 'sd-precision-tag--unavailable' in html
        assert 'sd-precision-tag--heuristic' in html
        assert 'sd-precision-tag--residual' in html

    def test_availability_table_exact_pill(self):
        """Availability table should render correct pill for exact=True."""
        req_data = {
            'kind': 'llm.request_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': _request_usage(),
                'buckets': [],
                'captured_context_preview': '',
                'attribution_notes': [],
                'timing': {'request_at': '—', 'response_at': '—', 'duration': '—'},
                'availability_rows': [
                    {
                        'field': 'input_tokens',
                        'label': 'input_tokens',
                        'exact': True,
                        'available': True,
                        'precision': 'provider_reported',
                        'source': 'provider_response',
                        'fill_strategy': '—',
                        'note': '',
                    },
                    {
                        'field': 'model',
                        'label': 'model',
                        'exact': False,
                        'available': True,
                        'precision': 'heuristic',
                        'source': 'log_file',
                        'fill_strategy': '从文件名推断',
                        'note': '',
                    },
                    {
                        'field': 'foo',
                        'label': 'foo',
                        'exact': False,
                        'available': False,
                        'precision': 'unavailable',
                        'source': '—',
                        'fill_strategy': '—',
                        'note': '',
                    },
                ],
            },
        }
        html = _render_payload_sources([req_data])
        assert 'sd-attribution-avail--ok' in html  # available -> 可用
        assert 'sd-attribution-avail--no' in html  # not available -> 不可用

    def test_response_attribution_meta_has_response_fields(self):
        """Response attribution topgrid should show total output, visible text, etc."""
        resp_data = {
            'kind': 'llm.response_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': {
                    'total_output': {'value': 2000, 'precision': 'provider_reported'},
                    'visible_text': {'value': 1500, 'precision': 'estimated'},
                    'tool_use': {'value': 400, 'precision': 'heuristic'},
                    'metadata': {'value': 100, 'precision': 'estimated'},
                    'coverage': {'value': 1900, 'precision': 'heuristic'},
                    'unknown': {'value': 100, 'precision': 'residual'},
                    'finish_reason': {'value': 'tool_use', 'precision': 'exact'},
                },
                'buckets': [],
                'availability_rows': [],
                'captured_output_preview': '',
                'attribution_notes': [],
            },
        }
        html = _render_payload_sources([resp_data])
        assert '总输出' in html
        assert '可见文本' in html
        assert '工具调用' in html
        assert '元数据' in html
        assert 'Finish reason' in html

    def test_response_finish_reason_optional(self):
        """Response attribution should handle missing finish_reason gracefully."""
        resp_data = {
            'kind': 'llm.response_attribution',
            'data': {
                'agent': 'claude_code',
                'model': 'claude-sonnet-4',
                'source_label': 'transcript',
                'confidence_label': '高',
                'request_id': 'req-abc',
                'call_id': 'call-001',
                'usage': {
                    'total_output': {'value': 2000, 'precision': 'provider_reported'},
                    'visible_text': {'value': 1500, 'precision': 'estimated'},
                    'tool_use': {'value': 400, 'precision': 'heuristic'},
                    'metadata': {'value': 100, 'precision': 'estimated'},
                    'coverage': {'value': 1900, 'precision': 'heuristic'},
                    'unknown': {'value': 100, 'precision': 'residual'},
                },
                'buckets': [],
                'availability_rows': [],
                'captured_output_preview': '',
                'attribution_notes': [],
            },
        }
        html = _render_payload_sources([resp_data])
        # Finish reason should not appear when not provided
        assert 'Finish reason' not in html
