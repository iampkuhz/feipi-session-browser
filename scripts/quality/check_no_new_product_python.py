#!/usr/bin/env python3
"""Gate: reject new product Python files in src/session_browser/.

This script enforces the Python retirement policy (P40). It scans
src/session_browser/ for .py files and fails if any file not in the
known allowlist is found in the product_runtime or product_web category.

Harness, quality, test, and dev_tool Python files are NOT restricted
by this gate -- only new product runtime or web Python is blocked.

Exit 0 on pass, exit 1 on fail.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repository root is two levels up from this script (scripts/quality/ -> repo root).
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent

# Allowlist of all existing product_runtime and product_web .py files.
# Generated from reports/python-runtime-inventory.json on 2026-06-25.
# New files must be written in Java, not Python.
ALLOWED_PRODUCT_PY_FILES: frozenset[str] = frozenset(
    {
        # -- product_runtime (122) --
        "src/session_browser/__init__.py",
        "src/session_browser/__main__.py",
        "src/session_browser/cli.py",
        "src/session_browser/config.py",
        "src/session_browser/attribution/__init__.py",
        "src/session_browser/attribution/context.py",
        "src/session_browser/attribution/contracts.py",
        "src/session_browser/attribution/dto.py",
        "src/session_browser/attribution/serializers.py",
        "src/session_browser/attribution/service.py",
        "src/session_browser/attribution/taxonomy.py",
        "src/session_browser/attribution/token_estimator.py",
        "src/session_browser/attribution/agents/__init__.py",
        "src/session_browser/attribution/agents/base.py",
        "src/session_browser/attribution/agents/claude_code_attribution_builder.py",
        "src/session_browser/attribution/agents/claude_code_tool_schemas.py",
        "src/session_browser/attribution/agents/codex_attribution_builder.py",
        "src/session_browser/attribution/agents/codex_request_taxonomy.py",
        "src/session_browser/attribution/agents/qoder_attribution_builder.py",
        "src/session_browser/attribution/agents/claude_code_parts/__init__.py",
        "src/session_browser/attribution/agents/claude_code_parts/claude_code_agent_tools.py",
        "src/session_browser/attribution/agents/claude_code_parts/utils.py",
        "src/session_browser/attribution/api_families/__init__.py",
        "src/session_browser/attribution/api_families/anthropic_messages/__init__.py",
        "src/session_browser/attribution/api_families/anthropic_messages/cache_allocator.py",
        "src/session_browser/attribution/api_families/anthropic_messages/normalizer.py",
        "src/session_browser/attribution/api_families/anthropic_messages/request_order.py",
        "src/session_browser/attribution/api_families/anthropic_messages/usage_parser.py",
        "src/session_browser/attribution/api_families/estimate_only/__init__.py",
        "src/session_browser/attribution/api_families/estimate_only/cache_estimator.py",
        "src/session_browser/attribution/api_families/estimate_only/normalizer.py",
        "src/session_browser/attribution/api_families/estimate_only/usage_estimator.py",
        "src/session_browser/attribution/api_families/openai_chat/__init__.py",
        "src/session_browser/attribution/api_families/openai_chat/cache_allocator.py",
        "src/session_browser/attribution/api_families/openai_chat/normalizer.py",
        "src/session_browser/attribution/api_families/openai_chat/request_order.py",
        "src/session_browser/attribution/api_families/openai_chat/usage_parser.py",
        "src/session_browser/attribution/api_families/openai_responses/__init__.py",
        "src/session_browser/attribution/api_families/openai_responses/cache_allocator.py",
        "src/session_browser/attribution/api_families/openai_responses/normalizer.py",
        "src/session_browser/attribution/api_families/openai_responses/request_order.py",
        "src/session_browser/attribution/api_families/openai_responses/usage_parser.py",
        "src/session_browser/attribution/api_families/qoder_broker/__init__.py",
        "src/session_browser/attribution/api_families/qoder_broker/credit_estimator.py",
        "src/session_browser/attribution/api_families/qoder_broker/credit_parser.py",
        "src/session_browser/attribution/api_families/qoder_broker/normalizer.py",
        "src/session_browser/attribution/api_families/qoder_broker/underlying_family_resolver.py",
        "src/session_browser/attribution/api_families/qoder_broker/usage_parser.py",
        "src/session_browser/attribution/collectors/agent_app/claude_code/__init__.py",
        "src/session_browser/attribution/collectors/agent_app/claude_code/builtins_catalog.py",
        "src/session_browser/attribution/collectors/agent_app/claude_code/system_prompt_extractor.py",
        "src/session_browser/attribution/collectors/agent_app/claude_code/tool_registry_extractor.py",
        "src/session_browser/attribution/collectors/agent_app/claude_code/tool_schema_normalizer.py",
        "src/session_browser/attribution/collectors/agent_app/codex/__init__.py",
        "src/session_browser/attribution/collectors/agent_app/codex/default_prompt_extractor.py",
        "src/session_browser/attribution/collectors/agent_app/codex/tool_schema_extractor.py",
        "src/session_browser/attribution/collectors/agent_app/qoder/__init__.py",
        "src/session_browser/attribution/collectors/agent_app/qoder/builtin_tools_catalog.py",
        "src/session_browser/attribution/collectors/agent_app/qoder/model_policy_reader.py",
        "src/session_browser/attribution/collectors/agent_app/qoder/rules_schema_reader.py",
        "src/session_browser/attribution/collectors/history/__init__.py",
        "src/session_browser/attribution/collectors/history/compact_summary_extractor.py",
        "src/session_browser/attribution/collectors/history/message_timeline_builder.py",
        "src/session_browser/attribution/collectors/history/prior_messages_extractor.py",
        "src/session_browser/attribution/collectors/history/prior_tool_results_extractor.py",
        "src/session_browser/attribution/collectors/project/__init__.py",
        "src/session_browser/attribution/collectors/project/agents_md_reader.py",
        "src/session_browser/attribution/collectors/project/claude_md_reader.py",
        "src/session_browser/attribution/collectors/project/file_snapshot_reader.py",
        "src/session_browser/attribution/collectors/project/mcp_config_reader.py",
        "src/session_browser/attribution/collectors/project/qoder_config_reader.py",
        "src/session_browser/attribution/collectors/project/qoder_rules_reader.py",
        "src/session_browser/attribution/collectors/project/repo_context_locator.py",
        "src/session_browser/attribution/collectors/project/subagent_prompt_reader.py",
        "src/session_browser/attribution/collectors/session/__init__.py",
        "src/session_browser/attribution/collectors/session/assistant_output.py",
        "src/session_browser/attribution/collectors/session/current_user_message.py",
        "src/session_browser/attribution/collectors/session/event_stream_reader.py",
        "src/session_browser/attribution/collectors/session/jsonl_reader.py",
        "src/session_browser/attribution/collectors/session/llm_call_locator.py",
        "src/session_browser/attribution/collectors/session/raw_payload_extractor.py",
        "src/session_browser/attribution/collectors/session/tool_result_extractor.py",
        "src/session_browser/attribution/collectors/session/tool_use_extractor.py",
        "src/session_browser/attribution/collectors/session/usage_extractor.py",
        "src/session_browser/attribution/core/__init__.py",
        "src/session_browser/attribution/core/bucket_aggregator.py",
        "src/session_browser/attribution/core/models.py",
        "src/session_browser/attribution/core/residuals.py",
        "src/session_browser/attribution/core/span_builder.py",
        "src/session_browser/attribution/core/validation.py",
        "src/session_browser/attribution/mapping/__init__.py",
        "src/session_browser/attribution/mapping/agent_runtime.py",
        "src/session_browser/attribution/mapping/api_family.py",
        "src/session_browser/attribution/mapping/call_mapping_resolver.py",
        "src/session_browser/attribution/mapping/model_string_detector.py",
        "src/session_browser/attribution/mapping/usage_shape_detector.py",
        "src/session_browser/attribution/mapping/agents/__init__.py",
        "src/session_browser/attribution/mapping/agents/claude_code_token_accounting_mapping.py",
        "src/session_browser/attribution/mapping/agents/codex_token_accounting_mapping.py",
        "src/session_browser/attribution/mapping/agents/qoder_token_accounting_mapping.py",
        "src/session_browser/attribution/tokenization/__init__.py",
        "src/session_browser/attribution/tokenization/heuristic_counter.py",
        "src/session_browser/attribution/tokenization/qoder_estimator.py",
        "src/session_browser/attribution/tokenization/router.py",
        "src/session_browser/attribution/tokenization/tiktoken_counter.py",
        "src/session_browser/domain/__init__.py",
        "src/session_browser/domain/_validation.py",
        "src/session_browser/domain/content_part.py",
        "src/session_browser/domain/enums.py",
        "src/session_browser/domain/llm_models.py",
        "src/session_browser/domain/message_models.py",
        "src/session_browser/domain/models.py",
        "src/session_browser/domain/normalizer.py",
        "src/session_browser/domain/project_models.py",
        "src/session_browser/domain/serializers.py",
        "src/session_browser/domain/session_models.py",
        "src/session_browser/domain/subagent_models.py",
        "src/session_browser/domain/token_models.py",
        "src/session_browser/domain/token_normalizer.py",
        "src/session_browser/domain/tool_models.py",
        "src/session_browser/domain/token_normalizers/__init__.py",
        "src/session_browser/domain/token_normalizers/codex_token_normalizer.py",
        # -- product_web (23) --
        "src/session_browser/web/__init__.py",
        "src/session_browser/web/mhtml.py",
        "src/session_browser/web/routes.py",
        "src/session_browser/web/safe_render.py",
        "src/session_browser/web/template_env.py",
        "src/session_browser/web/view_models.py",
        "src/session_browser/web/presenters/__init__.py",
        "src/session_browser/web/presenters/dashboard.py",
        "src/session_browser/web/presenters/projects.py",
        "src/session_browser/web/presenters/session_detail.py",
        "src/session_browser/web/presenters/sessions.py",
        "src/session_browser/web/renderers/__init__.py",
        "src/session_browser/web/renderers/llm_blocks.py",
        "src/session_browser/web/renderers/markdown.py",
        "src/session_browser/web/session_detail/__init__.py",
        "src/session_browser/web/session_detail/anomalies.py",
        "src/session_browser/web/session_detail/ids.py",
        "src/session_browser/web/session_detail/payloads.py",
        "src/session_browser/web/session_detail/preview.py",
        "src/session_browser/web/session_detail/render_helpers.py",
        "src/session_browser/web/session_detail/session_cache.py",
        "src/session_browser/web/session_detail/url_helpers.py",
        "src/session_browser/web/session_detail/view_model.py",
    }
)


def _scan_product_python(repo_root: Path) -> list[str]:
    """Return sorted list of .py file paths under src/session_browser/."""
    src_dir = repo_root / "src" / "session_browser"
    if not src_dir.is_dir():
        return []
    results: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        # Skip __pycache__
        if "__pycache__" in py_file.parts:
            continue
        rel = py_file.relative_to(repo_root).as_posix()
        results.append(rel)
    return results


def main() -> int:
    """Run the gate check. Returns 0 on pass, 1 on fail."""
    repo_root = _REPO_ROOT
    all_py = _scan_product_python(repo_root)

    violations: list[str] = []
    for rel_path in all_py:
        if rel_path not in ALLOWED_PRODUCT_PY_FILES:
            violations.append(rel_path)

    if violations:
        print(
            "FAIL: check_no_new_product_python -- "
            f"found {len(violations)} new product Python file(s) "
            "not in the allowlist:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nPython retirement policy (P40) prohibits adding new product "
            "runtime or web Python files.\n"
            "Write new functionality in Java instead.\n"
            "If this is an intentional exception, update the allowlist in\n"
            "scripts/quality/check_no_new_product_python.py and document "
            "the reason.",
            file=sys.stderr,
        )
        return 1

    print(
        f"PASS: check_no_new_product_python -- "
        f"all {len(all_py)} product Python files are in the allowlist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
