"""测试 scripts/quality/run_quality_gate.py 的质量门禁运行器."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import NoReturn

import pytest
from scripts.quality import run_quality_gate
from scripts.quality.quality_artifact import (
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
    compute_overall,
    write_quality_summary,
)
from scripts.quality.quality_targets import (
    applicable_gates_for_target,
    required_gates_for_target,
    validate_target,
)
from scripts.quality.run_quality_gate import build_summary

SCHEMA_VERSION = 3
PLAYWRIGHT_MIN_WORKERS = 8
PLAYWRIGHT_HIGH_WORKERS = 12


class TestComputeOverall:
    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_all_pass(self):
        status, failures = compute_overall({'a': 'PASS', 'b': 'PASS'})
        assert status == 'PASS'
        assert failures == []

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_single_fail(self):
        status, failures = compute_overall({'a': 'PASS', 'b': 'FAIL'})
        assert status == 'FAIL'
        assert any('b' in f for f in failures)

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_blocked(self):
        status, _failures = compute_overall({'a': 'BLOCKED'})
        assert status == 'FAIL'

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_skipped_is_failure(self):
        status, failures = compute_overall({'a': 'SKIPPED'})
        assert status == 'FAIL'
        assert any('SKIPPED' in f for f in failures)

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_empty_is_blocked(self):
        status, failures = compute_overall({})
        assert status == 'BLOCKED'
        assert failures


class TestBuildSummary:
    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_schema_version_3(self):
        started = '2026-01-01T00:00:00Z'
        details = [
            GateDetail(name='pytest', status=PASS, command=['pytest', '-q'], exitCode=0),
        ]
        summary = build_summary('session-detail', 'test', started, details)
        assert summary.schemaVersion == SCHEMA_VERSION
        assert summary.target == 'session-detail'
        assert summary.changeId == 'test'
        assert summary.status == PASS
        assert 'pytest' in summary.requiredGates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_blocking_in_summary(self):
        started = '2026-01-01T00:00:00Z'
        details = [
            GateDetail(
                name='css',
                status=FAIL,
                command=['python3', 'check.py'],
                exitCode=1,
                output='missing rule',
            ),
        ]
        summary = build_summary('session-detail', 'test', started, details)
        assert summary.status == FAIL
        assert len(summary.blockingFailures) >= 1


class TestWriteSummary:
    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_summary_written(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            started = '2026-01-01T00:00:00Z'
            details = [GateDetail(name='pytest', status=PASS)]
            summary = build_summary('session-detail', 'test', started, details)
            write_quality_summary(out, summary)
            summary_path = out / 'test' / 'quality-gate-summary.session-detail.json'
            assert summary_path.exists()
            data = json.loads(summary_path.read_text())
            assert data['schemaVersion'] == SCHEMA_VERSION
            assert data['target'] == 'session-detail'


class TestQualityTargets:
    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_hook_runtime_gates(self):
        gates = required_gates_for_target('hook-runtime')
        assert 'settingsJson' in gates
        assert 'bashSyntax' in gates
        assert 'pythonCompile' in gates
        assert 'noTestSkips' in gates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_session_detail_gates(self):
        gates = required_gates_for_target('session-detail')
        assert 'pytest' in gates
        assert 'pythonCompile' in gates
        assert 'noTestSkips' in gates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_validate_unknown_target(self):
        with pytest.raises(ValueError):
            validate_target('nonexistent')

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_acceptance_contract_gates(self):
        gates = required_gates_for_target('acceptance-contracts')
        assert 'noTestSkips' in gates
        assert 'acceptanceContracts' in gates
        assert 'pytest' in gates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_python_standard_gates_are_manual_capability(self):
        gates = required_gates_for_target('python-standard')
        assert gates == [
            'pythonFormat',
            'pythonLint',
            'pythonType',
            'pythonDocstring',
            'pythonCoverage',
            'pythonAudit',
            'pythonComplexity',
            'pythonDeadCode',
            'pythonDeps',
        ]

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_hook_runtime_runs_acceptance_contract_gate_for_validator_changes(self):
        gates = applicable_gates_for_target(
            'hook-runtime',
            ['scripts/quality/validate_acceptance_contracts.py'],
        )
        assert 'acceptanceContracts' in gates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_acceptance_contracts_runs_no_skip_gate_for_test_changes(self):
        gates = applicable_gates_for_target(
            'acceptance-contracts',
            ['tests/playwright/session-detail.spec.js'],
        )
        assert 'noTestSkips' in gates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_hook_runtime_runs_no_skip_gate_for_gate_changes(self):
        gates = applicable_gates_for_target(
            'hook-runtime',
            ['scripts/quality/check_no_test_skips.py'],
        )
        assert 'noTestSkips' in gates

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_hook_runtime_runs_doctor_for_python_tooling_config_changes(self):
        gates = applicable_gates_for_target(
            'hook-runtime',
            ['pyproject.toml', 'uv.lock', '.github/workflows/quality.yml'],
        )
        assert 'doctor' in gates
        assert 'repoStructure' in gates


class TestQualityGateRuntime:
    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_pytest_gate_uses_project_python_module(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(
            run_quality_gate,
            '_project_python',
            lambda repo_root, *, dev=False: '/tmp/dev-python' if dev else '/tmp/runtime-python',
        )
        tests_dir = tmp_path / 'tests' / 'ui'
        tests_dir.mkdir(parents=True)
        (tests_dir / 'test_web_template_contract.py').write_text('', encoding='utf-8')
        cmd = run_quality_gate.gate_command('pytest', tmp_path, 'session-detail')
        assert cmd[:4] == ['/tmp/dev-python', '-m', 'pytest', '-q']
        assert cmd[4:6] == ['-W', 'error']

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_no_test_skips_gate_command(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setattr(
            run_quality_gate,
            '_project_python',
            lambda repo_root, *, dev=False: '/tmp/runtime-python',
        )

        cmd = run_quality_gate.gate_command('noTestSkips', tmp_path, 'hook-runtime')

        assert cmd == ['/tmp/runtime-python', 'scripts/quality/check_no_test_skips.py']

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_python_standard_gate_commands_delegate_to_session_browser_script(self, tmp_path: Path):
        expected = {
            'pythonFormat': 'format-check',
            'pythonLint': 'lint',
            'pythonType': 'type',
            'pythonDocstring': 'doc',
            'pythonCoverage': 'coverage',
            'pythonAudit': 'audit',
            'pythonComplexity': 'complexity',
            'pythonDeadCode': 'dead-code',
            'pythonDeps': 'deps-check',
        }
        for gate, command in expected.items():
            assert run_quality_gate.gate_command(gate, tmp_path, 'python-standard') == [
                'bash',
                'scripts/session-browser.sh',
                command,
            ]

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_browser_layout_gate_includes_dashboard_chart_coordinates(self, tmp_path: Path):
        (tmp_path / 'tests' / 'playwright').mkdir(parents=True)
        (tmp_path / 'playwright.config.js').write_text('', encoding='utf-8')
        (tmp_path / 'node_modules').mkdir()

        cmd = run_quality_gate.gate_command('browserLayout', tmp_path, 'session-detail')

        assert 'dashboard-chart-coordinates' in cmd
        assert '--workers=8' in cmd
        assert '--workers=1' not in cmd

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_browser_interaction_gate_uses_parallel_workers(self, tmp_path: Path):
        (tmp_path / 'tests' / 'playwright').mkdir(parents=True)
        (tmp_path / 'playwright.config.js').write_text('', encoding='utf-8')
        (tmp_path / 'node_modules').mkdir()

        cmd = run_quality_gate.gate_command('browserInteraction', tmp_path, 'session-detail')

        assert 'sessions-list.spec.js' in cmd
        assert '--workers=8' in cmd
        assert '--workers=1' not in cmd

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_playwright_workers_clamps_low_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('SESSION_BROWSER_PLAYWRIGHT_WORKERS', '1')

        assert run_quality_gate._playwright_workers() == PLAYWRIGHT_MIN_WORKERS

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_playwright_workers_allows_higher_override(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv('SESSION_BROWSER_PLAYWRIGHT_WORKERS', str(PLAYWRIGHT_HIGH_WORKERS))

        assert run_quality_gate._playwright_workers() == PLAYWRIGHT_HIGH_WORKERS

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_selected_playwright_gate_fails_when_tests_skip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            'run',
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='2 passed\n1 skipped\n'),
        )

        detail = run_quality_gate.run_cmd(
            'browserInteraction',
            ['npx', 'playwright', 'test', 'session-detail.spec.js', '--workers=8'],
            tmp_path,
        )

        assert detail.status == FAIL
        assert 'selected Playwright gate reported 1 skipped tests' in detail.output

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_selected_gate_fails_when_output_reports_warning(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            'run',
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout='================ warnings summary ================\n'
                'test_warn.py::test_case\n'
                '  UserWarning: fixture warning\n'
                '1 passed, 1 warning\n',
            ),
        )

        detail = run_quality_gate.run_cmd(
            'pytest',
            ['python3', '-m', 'pytest', '-q', 'tests'],
            tmp_path,
        )

        assert detail.status == FAIL
        assert 'warning after trigger' in detail.output

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_css_ownership_warn_metadata_does_not_fail_warning_gate(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            'run',
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout='CSS Ownership Gate Report\n'
                'Warnings:           2\n\n'
                '--- Warnings ---\n'
                '  [WARN]  hardcoded-color (L1): page.css — known debt\n\n'
                'CSS ownership: PASS (2 warnings)\n',
            ),
        )

        detail = run_quality_gate.run_cmd(
            'cssOwnership',
            ['python3', 'scripts/quality/check_css_ownership.py'],
            tmp_path,
        )

        assert detail.status == PASS
        assert 'warning after trigger' not in detail.output

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_css_ownership_real_warning_still_fails_warning_gate(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            'run',
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout='CSS Ownership Gate Report\n'
                'Warnings:           1\n'
                'UserWarning: runtime warning from quality script\n'
                'CSS ownership: PASS (1 warning)\n',
            ),
        )

        detail = run_quality_gate.run_cmd(
            'cssOwnership',
            ['python3', 'scripts/quality/check_css_ownership.py'],
            tmp_path,
        )

        assert detail.status == FAIL
        assert 'UserWarning' in detail.output

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_playwright_env_removes_no_color_when_force_color_is_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        captured_env: dict[str, str] = {}
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setenv('FORCE_COLOR', '1')
        monkeypatch.setenv('NO_COLOR', '1')

        def fake_run(*args: object, **kwargs: dict[str, str]) -> SimpleNamespace:
            captured_env.update(kwargs['env'])
            return SimpleNamespace(returncode=0, stdout='1 passed\n')

        monkeypatch.setattr(run_quality_gate.subprocess, 'run', fake_run)

        detail = run_quality_gate.run_cmd(
            'browserLayout',
            ['npx', 'playwright', 'test', 'session-detail-layout', '--workers=8'],
            tmp_path,
        )

        assert detail.status == PASS
        assert captured_env['FORCE_COLOR'] == '1'
        assert 'NO_COLOR' not in captured_env

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_playwright_known_node_deprecation_noise_does_not_fail(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            'run',
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout=(
                    '(node:123) [DEP0205] DeprecationWarning: '
                    '`module.register()` is deprecated. '
                    'Use `module.registerHooks()` instead.\n'
                    '(Use `node --trace-warnings ...` to show where the warning was created)\n'
                    '1 passed\n'
                ),
            ),
        )

        detail = run_quality_gate.run_cmd(
            'browserLayout',
            ['npx', 'playwright', 'test', 'session-detail-layout', '--workers=8'],
            tmp_path,
        )

        assert detail.status == PASS

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_playwright_real_deprecation_warning_still_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(run_quality_gate.shutil, 'which', lambda name: name)
        monkeypatch.setattr(
            run_quality_gate.subprocess,
            'run',
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout=(
                    '(node:123) DeprecationWarning: test emitted deprecated API warning\n1 passed\n'
                ),
            ),
        )

        detail = run_quality_gate.run_cmd(
            'browserLayout',
            ['npx', 'playwright', 'test', 'session-detail-layout', '--workers=8'],
            tmp_path,
        )

        assert detail.status == FAIL
        assert 'DeprecationWarning' in detail.output

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_warning_after_trigger_is_recorded_in_summary(self):
        started = '2026-01-01T00:00:00Z'
        summary = build_summary(
            'hook-runtime',
            'test',
            started,
            [
                GateDetail(
                    name='pytest',
                    status=FAIL,
                    output=(
                        '[quality-gate] FAIL: warning after trigger: '
                        'selected gate reported 1 warning(s)'
                    ),
                )
            ],
            not_triggered_gates=['doctor'],
        )

        assert summary.status == FAIL
        assert summary.warnings == ['pytest: warning after trigger']
        assert summary.artifacts['notTriggeredGates'] == ['doctor']

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_fixture_playwright_gate_injects_session_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        captured_env: dict[str, str] = {}

        monkeypatch.setattr(
            run_quality_gate,
            'required_gates_for_target',
            lambda target: ['browserInteraction'],
        )
        monkeypatch.setattr(
            run_quality_gate,
            'gate_command',
            lambda gate, repo_root, target: [
                'npx',
                'playwright',
                'test',
                'session-detail.spec.js',
                '--workers=8',
            ],
        )
        monkeypatch.setattr(run_quality_gate, '_fixture_session_available', lambda base_url: True)

        def capture_run_cmd(
            name: str,
            cmd: list[str],
            cwd: Path,
            required: bool = True,
            env_overrides: dict[str, str] | None = None,
        ) -> GateDetail:
            del cwd, required
            captured_env.update(env_overrides or {})
            return GateDetail(name=name, status=PASS, command=cmd)

        monkeypatch.setattr(run_quality_gate, 'run_cmd', capture_run_cmd)

        details = run_quality_gate.run_target(tmp_path, 'session-detail')

        assert details[0].status == PASS
        assert captured_env['BASE_URL'] == 'http://127.0.0.1:19099'
        assert captured_env['PW_SESSION_URL'] == (
            'http://127.0.0.1:19099/sessions/claude_code/hifi-viz-session-001'
        )

    @pytest.mark.contract_case('HOOK-HARNESS-010')
    def test_fixture_gate_blocks_without_running_playwright(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(
            run_quality_gate,
            'required_gates_for_target',
            lambda target: ['browserLayout'],
        )
        monkeypatch.setattr(
            run_quality_gate,
            'gate_command',
            lambda gate, repo_root, target: ['npx', 'playwright', 'test', 'session-detail-layout'],
        )
        monkeypatch.setattr(run_quality_gate, '_fixture_session_available', lambda base_url: False)
        monkeypatch.setattr(
            run_quality_gate,
            '_start_fixture_server',
            lambda: (None, None, None, 'missing jinja2'),
        )

        def fail_if_called(*args: object, **kwargs: object) -> NoReturn:
            raise AssertionError('fixture-dependent Playwright gate should fail fast')

        monkeypatch.setattr(run_quality_gate, 'run_cmd', fail_if_called)

        details = run_quality_gate.run_target(tmp_path, 'session-detail')
        assert len(details) == 1
        assert details[0].name == 'browserLayout'
        assert details[0].status == BLOCKED
        assert 'missing jinja2' in details[0].output

    @pytest.mark.contract_case('HARNESS-GATE-PRUNE-001')
    def test_selected_target_runs_full_baseline_with_changed_files(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """changed-files 只传给子 gate，不裁剪已选 target 的 required baseline。"""
        gates = ['javaCheck', 'noJavaTestSkips']
        seen: list[str] = []
        env_by_gate: dict[str, dict[str, str]] = {}
        monkeypatch.setattr(run_quality_gate, 'required_gates_for_target', lambda target: gates)
        monkeypatch.setattr(
            run_quality_gate,
            'gate_command',
            lambda gate, repo_root, target: ['echo', gate],
        )

        def capture_run_cmd(
            name: str,
            cmd: list[str],
            cwd: Path,
            required: bool = True,
            env_overrides: dict[str, str] | None = None,
        ) -> GateDetail:
            del cmd, cwd, required
            seen.append(name)
            env_by_gate[name] = dict(env_overrides or {})
            return GateDetail(name=name, status=PASS, command=['echo', name])

        monkeypatch.setattr(run_quality_gate, 'run_cmd', capture_run_cmd)

        details = run_quality_gate.run_target(
            tmp_path,
            'java-src',
            ['java/core-domain/src/main/java/com/feipi/session/browser/core/SessionIdentity.java'],
        )

        assert [detail.name for detail in details] == gates
        assert seen == gates
        assert json.loads(env_by_gate['noJavaTestSkips']['QUALITY_CHANGED_FILES']) == [
            'java/core-domain/src/main/java/com/feipi/session/browser/core/SessionIdentity.java'
        ]

    @pytest.mark.contract_case('HARNESS-GATE-PRUNE-001')
    def test_manual_selected_target_summary_has_no_not_triggered_gates(self):
        """单 target runner 的 notTriggeredGates 语义固定为空。"""
        summary = build_summary(
            'java-src',
            'test',
            '2026-01-01T00:00:00Z',
            [
                GateDetail(name='javaCheck', status=PASS),
                GateDetail(name='noJavaTestSkips', status=PASS),
            ],
            not_triggered_gates=[],
        )

        assert summary.artifacts['notTriggeredGates'] == []


class TestJavaChineseCommentsGateCommand:
    """javaChineseComments gate 命令必须使用仓库内脚本。"""

    @pytest.mark.contract_case('JR-020-001')
    def test_gate_command_uses_repo_checker(self, tmp_path: Path):
        """gate 命令指向 scripts/quality/check_code_comment_language.py。"""
        checker = tmp_path / 'scripts' / 'quality' / 'check_code_comment_language.py'
        checker.parent.mkdir(parents=True)
        checker.write_text('# mock', encoding='utf-8')
        policy = tmp_path / 'config' / 'technical-terms.json'
        policy.parent.mkdir(parents=True)
        policy.write_text('{}', encoding='utf-8')

        cmd = run_quality_gate.gate_command('javaChineseComments', tmp_path, 'java-src')

        assert cmd, '仓库内脚本存在时命令不应为空'
        assert any('check_code_comment_language.py' in str(c) for c in cmd), (
            f'命令应包含仓库内检查脚本: {cmd}'
        )

    @pytest.mark.contract_case('JR-020-001')
    def test_gate_command_no_tmp_reference(self, tmp_path: Path):
        """gate 命令不得引用 tmp/ 目录下的脚本或术语文件。"""
        checker = tmp_path / 'scripts' / 'quality' / 'check_code_comment_language.py'
        checker.parent.mkdir(parents=True)
        checker.write_text('# mock', encoding='utf-8')

        cmd = run_quality_gate.gate_command('javaChineseComments', tmp_path, 'java-src')

        for part in cmd:
            part_str = str(part)
            assert 'tmp' not in part_str or str(tmp_path) in part_str, (
                f'命令不应引用 tmp 路径: {cmd}'
            )

    @pytest.mark.contract_case('JR-020-001')
    def test_gate_blocked_when_checker_absent(self, tmp_path: Path):
        """检查脚本不存在时返回空列表，由 run_cmd 报告 BLOCKED。"""
        cmd = run_quality_gate.gate_command('javaChineseComments', tmp_path, 'java-src')
        assert cmd == []


class TestReportHashInSummary:
    """build_summary 和 write_quality_summary 必须生成 reportHash。"""

    @pytest.mark.contract_case('JR-020-006')
    def test_written_summary_has_report_hash(self, tmp_path: Path):
        """write_quality_summary 写入的 artifact 包含 reportHash。"""
        started = '2026-01-01T00:00:00Z'
        details = [GateDetail(name='javaCheck', status=PASS, command=['./gradlew', 'check'], exitCode=0)]
        summary = build_summary('java-src', 'test', started, details)
        path = write_quality_summary(tmp_path, summary)
        data = json.loads(path.read_text())
        assert 'reportHash' in data
        assert len(data['reportHash']) == 12


class TestNoJavaTestSkipsGateCommand:
    """noJavaTestSkips gate 命令验证。"""

    @pytest.mark.contract_case('JR-020-005')
    def test_no_java_test_skips_uses_gradlew(self, tmp_path: Path):
        """noJavaTestSkips 必须通过 gradlew verifyNoSkippedJavaTests 执行。"""
        gradlew = tmp_path / 'gradlew'
        gradlew.write_text('#!/bin/sh\n', encoding='utf-8')

        cmd = run_quality_gate.gate_command('noJavaTestSkips', tmp_path, 'java-src')

        assert cmd == [str(gradlew), 'verifyNoSkippedJavaTests']

    @pytest.mark.contract_case('JR-020-005')
    def test_no_java_test_skips_blocked_without_gradlew(self, tmp_path: Path):
        """gradlew 不存在时返回空列表（BLOCKED）。"""
        cmd = run_quality_gate.gate_command('noJavaTestSkips', tmp_path, 'java-src')
        assert cmd == []

    @pytest.mark.contract_case('JR-020-005')
    def test_java_check_uses_gradlew_check(self, tmp_path: Path):
        """javaCheck 必须通过 gradlew check 执行。"""
        gradlew = tmp_path / 'gradlew'
        gradlew.write_text('#!/bin/sh\n', encoding='utf-8')

        cmd = run_quality_gate.gate_command('javaCheck', tmp_path, 'java-src')

        assert cmd == [str(gradlew), 'check']


class TestMultipleTargetHandling:
    """多 target 场景：去重、dominance 和并行执行。"""

    @pytest.mark.contract_case('JR-020-004')
    def test_java_src_gates_include_all_required(self):
        """java-src target 必须包含 javaCheck、javaChineseComments 和 noJavaTestSkips。"""
        from scripts.quality.quality_targets import required_gates_for_target
        gates = required_gates_for_target('java-src')
        assert 'javaCheck' in gates
        assert 'javaChineseComments' in gates
        assert 'noJavaTestSkips' in gates

    @pytest.mark.contract_case('JR-020-004')
    def test_dominance_java_src_absorbs_java_build(self):
        """dominance 语义：java-src includes java-build，集合包含关系。"""
        from scripts.claude_hooks.classify import DOMINANCE
        assert 'java-build' in DOMINANCE['java-src']['includes']

    @pytest.mark.contract_case('JR-020-004')
    def test_dominance_reverse_java_build_does_not_absorb_java_src(self):
        """反向验证：java-build 不得吸收 java-src。"""
        from scripts.claude_hooks.classify import DOMINANCE
        build_includes = DOMINANCE.get('java-build', {}).get('includes', [])
        assert 'java-src' not in build_includes
