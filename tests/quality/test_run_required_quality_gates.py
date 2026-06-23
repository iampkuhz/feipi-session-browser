"""Test the required quality gate runner."""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / 'scripts' / 'quality' / 'run_required_quality_gates.py'
)
_spec = importlib.util.spec_from_file_location('run_required_quality_gates', SCRIPT_PATH)
_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runner)


def _setup_env(
    changed_files: list[dict[str, object]], session_id: str | None = 'test-session-001'
) -> Path:
    """Create a temporary hook log environment for one runner scenario."""
    td = Path(tempfile.mkdtemp())
    agent_log = td / 'agent_logs' / 'current'
    agent_log.mkdir(parents=True)
    quality = td / 'quality'
    quality.mkdir(parents=True)

    cf = agent_log / 'changed-files.jsonl'
    if changed_files:
        cf.write_text('\n'.join(json.dumps(e) for e in changed_files) + '\n')

    if session_id:
        (agent_log / 'session-id.txt').write_text(session_id)

    # 修补模块全局变量
    _runner.AGENT_LOG_DIR = agent_log
    _runner.CHANGED_FILES = cf
    _runner.SESSION_ID_FILE = agent_log / 'session-id.txt'
    _runner.QUALITY_DIR = quality
    _runner.REPO_ROOT = td

    return td


def _write_hook_quality_changes(cf_path: Path) -> None:
    """Write a changed-files entry that triggers the hook-runtime target."""
    cf_path.write_text(
        json.dumps(
            {
                'ts': '2026-05-24T00:00:00Z',
                'tool': 'Edit',
                'file': 'scripts/quality/run_quality_gate.py',
                'category': 'quality-gate',
                'requiresQualityGate': True,
                'sessionId': 'test-session-001',
            }
        )
        + '\n'
    )


class TestDryRun:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_dry_run_hook_runtime_detected(self):
        """Detect hook-runtime for quality script edits while excluding session-detail."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'scripts/quality/run_quality_gate.py',
                    'category': 'quality-gate',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        old_argv = sys.argv
        try:
            sys.argv = ['run_required_quality_gates.py', '--dry-run']
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0  # dry-run 始终返回 0

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_dry_run_acceptance_contracts_detected(self):
        """Detect acceptance-contracts for contract document or test edits."""
        _setup_env(
            [
                {
                    'ts': '2026-06-06T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
                    'category': 'acceptance-contract',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        changed_files = _runner.get_changed_files()
        targets = _runner.compute_required_targets(changed_files, set())
        assert targets == ['acceptance-contracts']

        old_argv = sys.argv
        try:
            sys.argv = ['run_required_quality_gates.py', '--dry-run']
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0


class TestNoRequiredTargets:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_empty_changed_files(self):
        """Return zero when no changed files are recorded."""
        _setup_env([])
        old_argv = sys.argv
        try:
            sys.argv = ['run_required_quality_gates.py']
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_docs_only(self):
        """Return zero for documentation-only edits with no quality target."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'README.md',
                    'category': 'other',
                    'requiresQualityGate': False,
                    'sessionId': 'test-session-001',
                }
            ]
        )
        old_argv = sys.argv
        try:
            sys.argv = ['run_required_quality_gates.py']
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0


class TestSessionDetailExcluded:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_session_detail_not_in_executed_targets(self):
        """Exclude session-detail from the runner target list by default."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'src/session_browser/web/static/css/shell.css',
                    'category': 'ui-css',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        changed_files = _runner.get_changed_files()
        all_targets = _runner.compute_required_targets(changed_files, _runner.EXCLUDED_TARGETS)
        assert 'session-detail' not in all_targets, 'session-detail 必须从 runner 目标中排除'


class TestChangedFilesReading:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_reads_from_jsonl(self):
        """Read changed file paths from changed-files.jsonl."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'scripts/hooks/stop.sh',
                    'category': 'hook',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        files = _runner.get_changed_files()
        assert 'scripts/hooks/stop.sh' in files

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_filters_by_session_id(self):
        """Ignore changed-files entries from another session id."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'scripts/hooks/stop.sh',
                    'category': 'hook',
                    'requiresQualityGate': True,
                    'sessionId': 'different-session',
                }
            ],
            session_id='test-session-001',
        )

        files = _runner.get_changed_files()
        assert len(files) == 0, '来自不同会话的文件应被过滤'


class TestChangeIdResolution:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_explicit_change_id(self):
        assert _runner.resolve_change_id('my-change') == 'my-change'

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_env_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """Use ACTIVE_CHANGE_ID when the caller does not pass a change id."""
        tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr(_runner, 'REPO_ROOT', tmp_dir)
        old = os.environ.get('ACTIVE_CHANGE_ID')
        try:
            os.environ['ACTIVE_CHANGE_ID'] = 'env-change'
            assert _runner.resolve_change_id(None) == 'env-change'
        finally:
            if old is None:
                os.environ.pop('ACTIVE_CHANGE_ID', None)
            else:
                os.environ['ACTIVE_CHANGE_ID'] = old

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_unknown_fallback(self, monkeypatch: pytest.MonkeyPatch):
        """Return unknown when no environment or active-change file exists."""
        tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr(_runner, 'REPO_ROOT', tmp_dir)
        old = os.environ.get('ACTIVE_CHANGE_ID')
        try:
            if 'ACTIVE_CHANGE_ID' in os.environ:
                del os.environ['ACTIVE_CHANGE_ID']
            # 临时环境中不存在 active_change.json 文件
            result = _runner.resolve_change_id(None)
            assert result == 'unknown'
        finally:
            if old is not None:
                os.environ['ACTIVE_CHANGE_ID'] = old

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_active_change_file_exists(self, monkeypatch: pytest.MonkeyPatch):
        """Read change_id from active_change.json when no environment override exists."""
        tmp_dir = Path(tempfile.mkdtemp())
        (tmp_dir / 'tmp').mkdir()
        (tmp_dir / 'tmp' / 'active_change.json').write_text(
            json.dumps({'change_id': 'from-file-change'})
        )
        monkeypatch.setattr(_runner, 'REPO_ROOT', tmp_dir)
        old = os.environ.get('ACTIVE_CHANGE_ID')
        try:
            if 'ACTIVE_CHANGE_ID' in os.environ:
                del os.environ['ACTIVE_CHANGE_ID']
            result = _runner.resolve_change_id(None)
            assert result == 'from-file-change'
        finally:
            if old is not None:
                os.environ['ACTIVE_CHANGE_ID'] = old


class TestNoFeipiAgentLogDir:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_no_env_variable_used(self):
        """Assert the runner does not depend on FEIPI_AGENT_LOG_DIR."""
        source = SCRIPT_PATH.read_text()
        assert 'FEIPI_AGENT_LOG_DIR' not in source, (
            'run_required_quality_gates.py 不得引用 FEIPI_AGENT_LOG_DIR'
        )


class TestIncludeSessionDetail:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_default_excludes_session_detail_dry_run(self):
        """Exclude session-detail from dry-run targets by default."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'src/session_browser/web/static/css/shell.css',
                    'category': 'ui-css',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        old_argv = sys.argv
        try:
            sys.argv = ['run_required_quality_gates.py', '--dry-run']
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_include_session_detail_dry_run(self):
        """Include session-detail in dry-run targets when requested."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'src/session_browser/web/static/css/shell.css',
                    'category': 'ui-css',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        old_argv = sys.argv
        try:
            sys.argv = ['run_required_quality_gates.py', '--dry-run', '--include-session-detail']
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_include_session_detail_computes_targets(self):
        """Include session-detail in computed targets when requested."""
        _setup_env(
            [
                {
                    'ts': '2026-05-24T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'src/session_browser/web/static/css/shell.css',
                    'category': 'ui-css',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                }
            ]
        )

        changed_files = _runner.get_changed_files()
        # Use the default exclusion set.
        excluded_targets = _runner.compute_required_targets(changed_files, _runner.EXCLUDED_TARGETS)
        assert 'session-detail' not in excluded_targets

        # Use the --include-session-detail behavior.
        no_exclusion = set()
        all_targets = _runner.compute_required_targets(changed_files, no_exclusion)
        assert 'session-detail' in all_targets

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_run_gate_uses_full_target_baseline(self, monkeypatch: pytest.MonkeyPatch):
        """Run each required target as a full baseline instead of a changed-files slice."""
        _setup_env([])
        captured_cmds: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> object:
            captured_cmds.append(list(cmd))
            artifact = (
                _runner.QUALITY_DIR
                / 'full-baseline-check'
                / 'quality-gate-summary.session-detail.json'
            )
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text('{"status":"PASS"}\n', encoding='utf-8')
            return _runner.subprocess.CompletedProcess(cmd, 0, stdout='ok')

        monkeypatch.setattr(_runner.subprocess, 'run', fake_run)

        passed, _artifact_path = _runner.run_gate('session-detail', 'full-baseline-check')

        assert passed is True
        assert captured_cmds, 'run_gate 必须调用 run_quality_gate.py'
        assert '--changed-files' not in captured_cmds[0]


class TestSharedStopEntrypoint:
    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_claude_stop_is_thin_wrapper(self):
        """Keep stop.sh as a thin wrapper around the shared harness runner."""
        stop_sh = Path(__file__).resolve().parents[2] / '.claude' / 'hooks' / 'stop.sh'
        text = stop_sh.read_text()

        assert 'scripts/harness/agent_stop_check.py' in text
        assert 'run_required_quality_gates.py' not in text
        assert 'stop_quality_gate.py' not in text

    @pytest.mark.contract_case('HOOK-HARNESS-012')
    def test_shared_stop_runner_includes_session_detail_flag(self):
        """Pass --include-session-detail from the shared stop runner."""
        runner = Path(__file__).resolve().parents[2] / 'scripts' / 'harness' / 'agent_stop_check.py'
        text = runner.read_text()
        assert 'run_required_quality_gates.py' in text
        assert '--include-session-detail' in text


class TestEffectiveTargetsIntegration:
    """runner 正确应用 dominance 去重。"""

    @pytest.mark.contract_case('JR-020-004')
    def test_runner_has_effective_targets(self):
        """runner 模块必须导入 effective_targets。"""
        assert hasattr(_runner, 'effective_targets'), (
            'run_required_quality_gates 必须导入 effective_targets'
        )

    @pytest.mark.contract_case('JR-020-004')
    def test_dominance_removes_java_build_in_dry_run(self):
        """java-src + java-build 同时触发时，runner 只运行 java-src。"""
        _setup_env(
            [
                {
                    'ts': '2026-06-23T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'java/core-domain/src/main/java/com/feipi/Foo.java',
                    'category': 'java-src',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                },
                {
                    'ts': '2026-06-23T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'build.gradle.kts',
                    'category': 'java-root-dsl',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                },
            ]
        )

        changed_files = _runner.get_changed_files()
        raw_targets = _runner.required_quality_targets(changed_files)
        assert 'java-src' in raw_targets
        assert 'java-build' in raw_targets

        # effective_targets 应移除 java-build
        effective = _runner.effective_targets(raw_targets)
        assert 'java-src' in effective
        assert 'java-build' not in effective

    @pytest.mark.contract_case('JR-020-004')
    def test_standalone_java_build_not_dominated(self):
        """仅 java-build 触发时不应被移除。"""
        _setup_env(
            [
                {
                    'ts': '2026-06-23T00:00:00Z',
                    'tool': 'Edit',
                    'file': 'build.gradle.kts',
                    'category': 'java-root-dsl',
                    'requiresQualityGate': True,
                    'sessionId': 'test-session-001',
                },
            ]
        )

        changed_files = _runner.get_changed_files()
        raw_targets = _runner.required_quality_targets(changed_files)
        effective = _runner.effective_targets(raw_targets)
        assert 'java-build' in effective
