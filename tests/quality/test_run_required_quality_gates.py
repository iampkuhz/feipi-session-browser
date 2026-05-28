"""测试 scripts/quality/run_required_quality_gates.py。"""
import pytest
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "quality" / "run_required_quality_gates.py"
_spec = importlib.util.spec_from_file_location("run_required_quality_gates", SCRIPT_PATH)
_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runner)


def _setup_env(changed_files: list[dict], session_id: str | None = "test-session-001"):
    """创建包含 changed-files.jsonl 和可选 session-id.txt 的临时环境。"""
    td = Path(tempfile.mkdtemp())
    agent_log = td / "agent_logs" / "current"
    agent_log.mkdir(parents=True)
    quality = td / "quality"
    quality.mkdir(parents=True)

    cf = agent_log / "changed-files.jsonl"
    if changed_files:
        cf.write_text("\n".join(json.dumps(e) for e in changed_files) + "\n")

    if session_id:
        (agent_log / "session-id.txt").write_text(session_id)

    # 修补模块全局变量
    _runner.AGENT_LOG_DIR = agent_log
    _runner.CHANGED_FILES = cf
    _runner.SESSION_ID_FILE = agent_log / "session-id.txt"
    _runner.QUALITY_DIR = quality
    _runner.REPO_ROOT = td

    return td


def _write_hook_quality_changes(cf_path: Path):
    """写入触发 hook-runtime 目标的 changed-files 条目。"""
    cf_path.write_text(json.dumps({
        "ts": "2026-05-24T00:00:00Z",
        "tool": "Edit",
        "file": "scripts/quality/run_quality_gate.py",
        "category": "quality-gate",
        "requiresQualityGate": True,
        "sessionId": "test-session-001",
    }) + "\n")


class TestDryRun:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_dry_run_hook_runtime_detected(self):
        """变更文件包含 scripts/quality/*.py => hook-runtime 出现在必需目标中，session-detail 被跳过。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "scripts/quality/run_quality_gate.py",
            "category": "quality-gate",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py", "--dry-run"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0  # dry-run 始终返回 0


class TestNoRequiredTargets:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_empty_changed_files(self):
        """无变更文件 => 退出码 0。"""
        td = _setup_env([])
        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_docs_only(self):
        """仅文档变更 => 无质量目标 => 退出码 0。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "README.md",
            "category": "other",
            "requiresQualityGate": False,
            "sessionId": "test-session-001",
        }])
        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0


class TestSessionDetailExcluded:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_session_detail_not_in_executed_targets(self):
        """UI 文件变更 => session-detail 在必需目标中但被 runner 排除。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        changed_files = _runner.get_changed_files()
        all_targets = _runner.compute_required_targets(changed_files, _runner.EXCLUDED_TARGETS)
        assert "session-detail" not in all_targets, \
            "session-detail 必须从 runner 目标中排除"


class TestChangedFilesReading:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_reads_from_jsonl(self):
        """应从 changed-files.jsonl 读取变更文件。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "scripts/hooks/stop.sh",
            "category": "hook",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        files = _runner.get_changed_files()
        assert "scripts/hooks/stop.sh" in files

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_filters_by_session_id(self):
        """不同 sessionId 的文件应被过滤掉。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "scripts/hooks/stop.sh",
            "category": "hook",
            "requiresQualityGate": True,
            "sessionId": "different-session",
        }], session_id="test-session-001")

        files = _runner.get_changed_files()
        assert len(files) == 0, "来自不同会话的文件应被过滤"


class TestChangeIdResolution:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_explicit_change_id(self):
        assert _runner.resolve_change_id("my-change") == "my-change"

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_env_fallback(self, monkeypatch):
        """设置 ACTIVE_CHANGE_ID 环境变量时应返回该值。"""
        tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr(_runner, "REPO_ROOT", tmp_dir)
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            os.environ["ACTIVE_CHANGE_ID"] = "env-change"
            assert _runner.resolve_change_id(None) == "env-change"
        finally:
            if old is None:
                os.environ.pop("ACTIVE_CHANGE_ID", None)
            else:
                os.environ["ACTIVE_CHANGE_ID"] = old

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_unknown_fallback(self, monkeypatch):
        """无环境变量且无 active-change 文件时，返回 'unknown'。"""
        tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr(_runner, "REPO_ROOT", tmp_dir)
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            if "ACTIVE_CHANGE_ID" in os.environ:
                del os.environ["ACTIVE_CHANGE_ID"]
            # 临时环境中不存在 active-change 文件
            result = _runner.resolve_change_id(None)
            assert result == "unknown"
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_active_change_file_exists(self, monkeypatch):
        """active-change 文件存在且无环境变量时，返回文件内容。"""
        tmp_dir = Path(tempfile.mkdtemp())
        (tmp_dir / "tmp").mkdir()
        (tmp_dir / "tmp" / "active-change").write_text("from-file-change")
        monkeypatch.setattr(_runner, "REPO_ROOT", tmp_dir)
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            if "ACTIVE_CHANGE_ID" in os.environ:
                del os.environ["ACTIVE_CHANGE_ID"]
            result = _runner.resolve_change_id(None)
            assert result == "from-file-change"
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old


class TestNoFeipiAgentLogDir:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_no_env_variable_used(self):
        """验证脚本不引用 FEIPI_AGENT_LOG_DIR。"""
        source = SCRIPT_PATH.read_text()
        assert "FEIPI_AGENT_LOG_DIR" not in source, \
            "run_required_quality_gates.py 不得引用 FEIPI_AGENT_LOG_DIR"


class TestIncludeSessionDetail:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_default_excludes_session_detail_dry_run(self):
        """默认行为：session-detail 从 dry-run 目标中排除。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py", "--dry-run"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_include_session_detail_dry_run(self):
        """--include-session-detail：session-detail 出现在 dry-run 目标中。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py", "--dry-run", "--include-session-detail"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_include_session_detail_computes_targets(self):
        """--include-session-detail：compute_required_targets 包含 session-detail。"""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        changed_files = _runner.get_changed_files()
        # 使用排除（默认）
        excluded_targets = _runner.compute_required_targets(changed_files, _runner.EXCLUDED_TARGETS)
        assert "session-detail" not in excluded_targets

        # 不使用排除（--include-session-detail）
        no_exclusion = set()
        all_targets = _runner.compute_required_targets(changed_files, no_exclusion)
        assert "session-detail" in all_targets


class TestStopShOrdering:
    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_run_required_before_stop_quality_gate(self):
        """stop.sh 必须在 stop_quality_gate.py 之前调用 run_required_quality_gates.py。"""
        stop_sh = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "stop.sh"
        text = stop_sh.read_text()

        run_required_pos = text.find("run_required_quality_gates.py")
        stop_quality_pos = text.find("stop_quality_gate.py")

        assert run_required_pos != -1, "stop.sh 中未找到 run_required_quality_gates.py"
        assert stop_quality_pos != -1, "stop.sh 中未找到 stop_quality_gate.py"
        assert run_required_pos < stop_quality_pos, \
            f"run_required_quality_gates.py (位置 {run_required_pos}) 必须出现在 stop_quality_gate.py (位置 {stop_quality_pos}) 之前"

    @pytest.mark.contract_case("HOOK-HARNESS-012")
    def test_stop_sh_includes_session_detail_flag(self):
        """stop.sh 必须向 run_required_quality_gates.py 传递 --include-session-detail。"""
        stop_sh = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "stop.sh"
        text = stop_sh.read_text()
        assert "--include-session-detail" in text, \
            "stop.sh 必须向 run_required_quality_gates.py 传递 --include-session-detail"
