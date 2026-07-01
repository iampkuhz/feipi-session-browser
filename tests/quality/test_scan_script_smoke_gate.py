"""Gate self-tests for scan-script-smoke target.

Verifies:
1. Changed files matching scan-related paths trigger scan-script-smoke
2. scan-script-smoke target can be validated
3. Gate command mapping returns correct command
4. Quality gate dispatch includes scan-script-smoke when triggered
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

from scripts.claude_hooks.classify import (  # noqa: E402
    SCAN_SCRIPT_SMOKE_PATTERNS,
    required_quality_targets,
)
from scripts.quality.quality_targets import (  # noqa: E402
    QUALITY_TARGETS,
    applicable_gates_for_target,
    required_gates_for_target,
    validate_target,
)


class TestScanScriptSmokeTrigger:
    """Verify changed-files trigger rules for scan-script-smoke."""

    def test_session_browser_sh_triggers_scan_script_smoke(self):
        """scripts/session-browser.sh should trigger scan-script-smoke."""
        targets = required_quality_targets(['scripts/session-browser.sh'])
        assert 'scan-script-smoke' in targets, (
            f'scripts/session-browser.sh should trigger scan-script-smoke, got: {targets}'
        )

    def test_java_scan_engine_triggers_scan_script_smoke(self):
        """java/scan-engine/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/scan-engine/src/main/java/com/feipi/scan/FullScanEngine.java'
        ])
        assert 'scan-script-smoke' in targets, (
            f'java/scan-engine/** should trigger scan-script-smoke, got: {targets}'
        )

    def test_java_source_claude_triggers_scan_script_smoke(self):
        """java/source-claude/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/source-claude/src/main/java/com/feipi/claude/ClaudeSourceAdapter.java'
        ])
        assert 'scan-script-smoke' in targets

    def test_java_source_codex_triggers_scan_script_smoke(self):
        """java/source-codex/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/source-codex/src/main/java/com/feipi/codex/CodexSourceAdapter.java'
        ])
        assert 'scan-script-smoke' in targets

    def test_java_source_qoder_triggers_scan_script_smoke(self):
        """java/source-qoder/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/source-qoder/src/main/java/com/feipi/qoder/QoderSourceAdapter.java'
        ])
        assert 'scan-script-smoke' in targets

    def test_java_index_sqlite_triggers_scan_script_smoke(self):
        """java/index-sqlite/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/index-sqlite/src/main/java/com/feipi/index/ConnectionFactory.java'
        ])
        assert 'scan-script-smoke' in targets

    def test_java_app_cli_triggers_scan_script_smoke(self):
        """java/app-cli/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/app-cli/src/main/java/com/feipi/cli/ScanCommand.java'
        ])
        assert 'scan-script-smoke' in targets

    def test_scripts_quality_triggers_scan_script_smoke(self):
        """scripts/quality/** should trigger scan-script-smoke."""
        targets = required_quality_targets([
            'scripts/quality/run_quality_gate.py'
        ])
        assert 'scan-script-smoke' in targets

    def test_unrelated_file_does_not_trigger_scan_script_smoke(self):
        """Unrelated files should NOT trigger scan-script-smoke."""
        targets = required_quality_targets([
            'java/web/src/main/resources/static/css/main.css'
        ])
        assert 'scan-script-smoke' not in targets

    def test_multiple_files_dedup_scan_script_smoke(self):
        """Multiple matching files should only add scan-script-smoke once."""
        targets = required_quality_targets([
            'scripts/session-browser.sh',
            'java/scan-engine/src/main/java/com/feipi/scan/FullScanEngine.java',
            'java/source-claude/src/main/java/com/feipi/claude/ClaudeSourceAdapter.java',
        ])
        count = sum(1 for t in targets if t == 'scan-script-smoke')
        assert count == 1, f'scan-script-smoke should appear exactly once, got {count}'


class TestScanScriptSmokeTargetValidation:
    """Verify scan-script-smoke target is properly registered."""

    def test_target_exists_in_quality_targets(self):
        """scan-script-smoke should be in QUALITY_TARGETS."""
        assert 'scan-script-smoke' in QUALITY_TARGETS

    def test_validate_target_accepts_scan_script_smoke(self):
        """validate_target should not raise for scan-script-smoke."""
        validate_target('scan-script-smoke')

    def test_required_gates_for_target(self):
        """required_gates_for_target should return scanScriptSmoke gate."""
        gates = required_gates_for_target('scan-script-smoke')
        assert 'scanScriptSmoke' in gates

    def test_applicable_gates_with_changed_files(self):
        """applicable_gates_for_target should include scanScriptSmoke when triggered."""
        changed_files = ['scripts/session-browser.sh']
        gates = applicable_gates_for_target('scan-script-smoke', changed_files)
        assert 'scanScriptSmoke' in gates


class TestScanScriptSmokeGateCommand:
    """Verify gate command mapping returns correct command."""

    def test_gate_command_returns_pytest_command(self):
        """gate_command should return pytest command for scanScriptSmoke."""
        from scripts.quality.run_quality_gate import gate_command

        cmd = gate_command('scanScriptSmoke', REPO_ROOT, 'scan-script-smoke')
        assert cmd, 'gate_command should return non-empty command'
        assert 'pytest' in ' '.join(cmd)
        assert 'test_session_browser_scan_smoke.py' in ' '.join(cmd)

    def test_gate_command_returns_empty_when_test_missing(self, tmp_path):
        """gate_command should return empty list when test file is missing."""
        from scripts.quality.run_quality_gate import gate_command

        # Use a fake repo root where the test file doesn't exist
        cmd = gate_command('scanScriptSmoke', tmp_path, 'scan-script-smoke')
        assert cmd == [], f'gate_command should return empty list when test missing, got: {cmd}'


class TestScanScriptSmokePatterns:
    """Verify SCAN_SCRIPT_SMOKE_PATTERNS contains expected paths."""

    def test_patterns_include_session_browser_sh(self):
        assert 'scripts/session-browser.sh' in SCAN_SCRIPT_SMOKE_PATTERNS

    def test_patterns_include_java_modules(self):
        expected = [
            'java/app-cli/**',
            'java/scan-engine/**',
            'java/source-claude/**',
            'java/source-codex/**',
            'java/source-qoder/**',
            'java/index-sqlite/**',
        ]
        for pattern in expected:
            assert pattern in SCAN_SCRIPT_SMOKE_PATTERNS, (
                f'{pattern} should be in SCAN_SCRIPT_SMOKE_PATTERNS'
            )
