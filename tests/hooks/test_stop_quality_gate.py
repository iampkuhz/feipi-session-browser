"""stop_quality_gate.py 脚本测试。"""
import pytest
import importlib.util
import json
import tempfile
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "stop_quality_gate.py"
_spec = importlib.util.spec_from_file_location("stop_quality_gate", SCRIPT_PATH)
_sqg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sqg)


def _make_artifact(status: str, finished: str = "2026-05-18T00:01:00Z") -> dict:
    return {
        "schemaVersion": 1,
        "status": status,
        "target": "session-detail",
        "changeId": "test",
        "startedAt": "2026-05-18T00:00:00Z",
        "finishedAt": finished,
        "requiredGates": {},
        "blockingFailures": [],
        "warnings": [],
        "artifacts": {},
    }


def _setup_env(changed_files_content: list[dict], artifact: dict | None = None, change_id: str = "test"):
    """使用 changed-files 和可选 artifact 创建临时测试环境。"""
    td = tempfile.mkdtemp()
    p = Path(td)
    cf = p / "changed-files.jsonl"
    qd = p / "quality" / change_id
    if changed_files_content:
        cf.write_text("\n".join(json.dumps(e) for e in changed_files_content) + "\n")
    if artifact is not None:
        qd.mkdir(parents=True, exist_ok=True)
        (qd / "quality-gate-summary.json").write_text(json.dumps(artifact))

    # 修补模块全局变量
    _sqg.CHANGED_FILES = cf
    _sqg.QUALITY_DIR = p / "quality"
    return p


class TestNoChangedFiles:
    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_no_files_pass(self):
        _setup_env([])
        status, msgs = _sqg.run_check("test")
        assert status == "PASS"


class TestUiChanges:
    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_missing_artifact_fails(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css", "requiresQualityGate": True,
        }])
        status, msgs = _sqg.run_check("test")
        assert status == "FAIL"
        assert any("missing" in m.lower() for m in msgs)

    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_artifact_fail_fails(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=_make_artifact("FAIL"))
        status, msgs = _sqg.run_check("test")
        assert status == "FAIL"

    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_artifact_stale_fails(self):
        _setup_env([{
            "ts": "2026-05-18T00:02:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=_make_artifact("PASS", finished="2026-05-18T00:01:00Z"))
        status, msgs = _sqg.run_check("test")
        assert status == "FAIL"

    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_artifact_fresh_passes(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=_make_artifact("PASS", finished="2026-05-18T00:01:00Z"))
        status, msgs = _sqg.run_check("test")
        assert status == "PASS"


class TestDocsOnly:
    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_non_ui_passes(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "README.md",
            "category": "other", "requiresQualityGate": False,
        }])
        status, msgs = _sqg.run_check("test")
        assert status == "PASS"


class TestFreshArtifactAfterRunner:
    """场景：run_required_quality_gates.py 刚运行并创建了最新 artifact，
    stop_quality_gate.py 应返回 PASS，因为 artifact 是新鲜的。"""

    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_fresh_artifact_from_runner_passes(self):
        """UI 文件被修改，runner 刚创建 PASS artifact，stop_quality_gate 应 PASS。"""
        now_ts = "2026-05-24T10:00:00Z"
        # Artifact 完成时间晚于 UI 编辑（新鲜的）
        artifact = _make_artifact("PASS", finished="2026-05-24T10:00:30Z")
        _setup_env([{
            "ts": now_ts, "tool": "Edit",
            "file": "src/session_browser/web/static/css/shell.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=artifact)
        status, msgs = _sqg.run_check("test")
        assert status == "PASS", f"Expected PASS with fresh artifact, got {status}: {msgs}"


class TestNoFeipiAgentLogDir:
    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_stop_quality_gate_no_feipi_agent_log_dir(self):
        """stop_quality_gate.py 不得引用 FEIPI_AGENT_LOG_DIR。"""
        source = SCRIPT_PATH.read_text()
        assert "FEIPI_AGENT_LOG_DIR" not in source, \
            "stop_quality_gate.py must not reference FEIPI_AGENT_LOG_DIR"

    @pytest.mark.contract_case("HOOK-HARNESS-006")
    def test_stop_check_targets_no_feipi_agent_log_dir(self):
        """stop_check_targets.py 不得引用 FEIPI_AGENT_LOG_DIR。"""
        script = Path(__file__).resolve().parents[2] / "scripts" / "quality" / "stop_check_targets.py"
        source = script.read_text()
        assert "FEIPI_AGENT_LOG_DIR" not in source, \
            "stop_check_targets.py must not reference FEIPI_AGENT_LOG_DIR"
