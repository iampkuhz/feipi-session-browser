#!/usr/bin/env python3
"""Deterministic quality gate runner.

按指定 target 运行质量门禁检查，并写入结构化 summary artifact。

用法:
    python3 scripts/quality/run_quality_gate.py --target session-detail --change-id fix-xyz
    python3 scripts/quality/run_quality_gate.py --target hook-runtime --change-id hook-runtime-selftest
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import shutil
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# 确保 repo_root 在 sys.path 中，使 `scripts.*` 导入在直接运行时可用。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality.quality_artifact import (
    GateDetail,
    QualitySummary,
    compute_overall,
    utc_now,
    write_quality_summary,
    PASS,
    FAIL,
    BLOCKED,
)
from scripts.quality.quality_targets import required_gates_for_target, applicable_gates_for_target, validate_target


# 01. 命令执行工具

def _fixture_session_available(base_url: str) -> bool:
    """Check if the HIFI fixture session is available on the given server."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"{base_url}/sessions/claude_code/hifi-viz-session-001", timeout=5)
        return resp.status == 200
    except Exception:
        return False


def _start_fixture_server() -> tuple[subprocess.Popen | None, str | None, str | None]:
    """Start a temporary fixture server with HIFI test data.

    Returns (proc, base_url, tmpdir) or (None, None, None) on failure.
    """
    import socket
    import tempfile
    import shutil
    import sqlite3

    fixture_root = REPO_ROOT / "tests" / "fixtures" / "session_hifi_fixture"
    if not fixture_root.exists():
        return None, None, None

    tmpdir = tempfile.mkdtemp(prefix="quality_gate_fixture_")
    index_dir = os.path.join(tmpdir, "index")
    os.makedirs(index_dir)
    sqlite_path = os.path.join(index_dir, "index.sqlite")
    data_dir = os.path.join(tmpdir, "claude_data")
    shutil.copytree(str(fixture_root), data_dir)

    # Populate index from fixture
    try:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        os.environ["CLAUDE_DATA_DIR"] = data_dir
        # Reload config to pick up new CLAUDE_DATA_DIR
        if "session_browser.config" in sys.modules:
            import importlib
            importlib.reload(sys.modules["session_browser.config"])
        for _mod in list(sys.modules):
            if _mod.startswith("session_browser.sources"):
                del sys.modules[_mod]

        from session_browser.index.indexer import init_schema, upsert_session
        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        from session_browser.sources.claude import scan_all_sessions
        for summary in scan_all_sessions():
            upsert_session(conn, summary)
        conn.commit()
        conn.close()
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None, None, None

    # Find free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["INDEX_DIR"] = index_dir
    env["CLAUDE_DATA_DIR"] = data_dir
    env["SERVER_HOST"] = "127.0.0.1"
    env["SERVER_PORT"] = str(port)
    env["SESSION_BROWSER_LOG_LEVEL"] = "WARNING"

    proc = subprocess.Popen(
        [sys.executable, "-m", "session_browser", "serve", "--allow-empty", "--no-scan"],
        cwd=str(REPO_ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # Wait for server to start
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            resp = urllib.request.urlopen(f"{base_url}/dashboard", timeout=2)
            if resp.status == 200:
                return proc, base_url, tmpdir
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    proc.wait()
    shutil.rmtree(tmpdir, ignore_errors=True)
    return None, None, None


def _stop_fixture_server(proc: subprocess.Popen, tmpdir: str | None) -> None:
    """Stop the fixture server and clean up temp files."""
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()


def run_cmd(name: str, cmd: list[str], cwd: Path, required: bool = True,
            env_overrides: dict[str, str] | None = None) -> GateDetail:
    started = time.time()
    if not cmd or shutil.which(cmd[0]) is None:
        status = BLOCKED if required else FAIL
        return GateDetail(name=name, status=status, command=cmd, durationMs=0, output=f"命令不存在：{cmd[0] if cmd else '<empty>'}")

    # Playwright 测试在并行化后应在 20s 内完成，120s 足够
    timeout = 120 if cmd[:2] == ["npx", "playwright"] else 300

    # Build env with optional overrides
    run_env = os.environ.copy()
    if env_overrides:
        run_env.update(env_overrides)

    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout, env=run_env)
        duration = int((time.time() - started) * 1000)
        output = (proc.stdout or "").strip()
        if len(output) > 4000:
            output = output[-4000:]
        return GateDetail(
            name=name,
            status=PASS if proc.returncode == 0 else FAIL,
            command=cmd,
            exitCode=proc.returncode,
            durationMs=duration,
            output=output,
        )
    except subprocess.TimeoutExpired as exc:
        return GateDetail(name=name, status=FAIL, command=cmd, durationMs=int((time.time() - started) * 1000), output=f"超时：{exc}")


# 02. gate 命令映射
def gate_command(gate: str, repo_root: Path, target: str) -> list[str]:
    if gate == "settingsJson":
        json_files = [".claude/settings.json", ".codex/hooks.json"]
        existing = [f for f in json_files if (repo_root / f).exists()]
        code = "import json,sys; [json.load(open(p, encoding='utf-8')) for p in sys.argv[1:]]"
        return [sys.executable, "-c", code, *existing] if existing else []
    if gate == "bashSyntax":
        shell_files = [
            ".claude/hooks/stop.sh",
            ".codex/hooks/pre_tool_guard.sh",
            ".codex/hooks/post_tool_guard.sh",
            ".codex/hooks/stop_check.sh",
            ".qoder/hooks/stop_check.sh",
            "scripts/harness/doctor.sh",
        ]
        existing = [f for f in shell_files if (repo_root / f).exists()]
        return ["bash", "-n", *existing] if existing else []
    if gate == "pythonCompile":
        paths = ["scripts/claude_hooks", "scripts/quality"]
        if target == "python-src":
            paths = ["src"]
        if target == "harness":
            paths = ["scripts/harness", "scripts/quality"]
        if target == "index":
            paths = ["src/session_browser/index", "scripts/quality/check_index_integrity.py"]
        return ["python3", "-m", "compileall", "-q", *paths]
    if gate == "hookSelfTest":
        return ["python3", "-m", "scripts.claude_hooks.main", "--self-test"]
    if gate == "templateContract":
        return ["python3", "scripts/quality/template_contract_check.py"]
    if gate == "staticCssContract":
        return ["python3", "scripts/quality/static_contract_check.py"]
    if gate == "cssOwnership":
        return ["python3", "scripts/quality/check_css_ownership.py"]
    if gate == "browserLayout":
        if (repo_root / "tests" / "playwright").exists() and (repo_root / "playwright.config.js").exists() and (repo_root / "node_modules").exists():
            return ["npx", "playwright", "test", "session-detail-layout", "shell-states"]
        return []
    if gate == "browserInteraction":
        if (repo_root / "tests" / "playwright").exists() and (repo_root / "playwright.config.js").exists() and (repo_root / "node_modules").exists():
            return ["npx", "playwright", "test", "session-detail.spec.js", "sessions-list.spec.js", "--grep-invert", "100 轮"]
        return []
    if gate == "pytest":
        test_candidates = {
            "session-detail": ["tests/ui/test_web_template_contract.py", "tests/ui/test_web_static_contract.py"],
            "python-src": [
                "tests/backend",
                "tests/test_llm_attribution_api.py",
                "tests/test_llm_attribution_bucket_normalization.py",
                "tests/test_llm_attribution_call_scoped_correctness.py",
                "tests/test_llm_attribution_claude_code.py",
                "tests/test_llm_attribution_codex.py",
                "tests/test_llm_attribution_context_builder.py",
                "tests/test_llm_attribution_context_hydration.py",
                "tests/test_llm_attribution_contract.py",
                "tests/test_llm_attribution_deep_source_correlation.py",
                "tests/test_llm_attribution_error_isolation.py",
                "tests/test_llm_attribution_error_payload.py",
                "tests/test_llm_attribution_qoder.py",
                "tests/test_llm_attribution_semantic_correctness.py",
                "tests/test_llm_attribution_serializers.py",
                "tests/test_llm_attribution_token_estimator.py",
                "tests/test_llm_attribution_visual_gate.py",
                "tests/test_codex_openai_attribution.py",
            ],
            "hook-runtime": [
                "tests/hooks/test_claude_hooks_hook_io.py",
                "tests/hooks/test_claude_hooks_classify.py",
                "tests/hooks/test_claude_hooks_bash_policy.py",
                "tests/hooks/test_claude_hooks_file_policy.py",
                "tests/hooks/test_claude_hooks_evidence.py",
                "tests/quality/test_quality_artifact.py",
            ],
            "acceptance-contracts": [
                "tests/quality/test_contract_case_specs.py",
            ],
            "index": ["tests/index/"],
        }
        items = [x for x in test_candidates.get(target, ["tests"]) if (repo_root / x).exists()]
        return ["pytest", "-q", *items] if items else []
    if gate == "doctor":
        return ["bash", "scripts/harness/doctor.sh"]
    if gate == "repoStructure":
        return ["python3", "scripts/quality/validate_repo_structure.py"]
    if gate == "harnessStructure":
        return ["python3", "scripts/harness/validate_harness_structure.py"]
    if gate == "openspecLayout":
        return ["python3", "scripts/harness/validate_openspec_layout.py"]
    if gate == "repoSlimming":
        return ["python3", "scripts/quality/repo_slimming_contract_check.py"]
    if gate == "indexIntegrity":
        return ["python3", "scripts/quality/check_index_integrity.py"]
    if gate == "rawInnerhtml":
        return ["python3", "scripts/quality/check_raw_innerhtml.py", "--check"]
    if gate == "layoutInlineStyle":
        return ["python3", "scripts/quality/check_layout_inline_style.py", "--check"]
    if gate == "acceptanceContracts":
        return [sys.executable, "scripts/quality/validate_acceptance_contracts.py"]
    return []


# 03. target 执行

# Gates that require the HIFI fixture session (need `hifi-viz-session-001`).
_FIXTURE_GATES = {"browserLayout", "browserInteraction"}


def run_target(repo_root: Path, target: str, changed_files: list[str] | None = None) -> list[GateDetail]:
    details: list[GateDetail] = []

    # Check if any fixture-dependent gate will run
    needs_fixture = any(g in _FIXTURE_GATES for g in applicable_gates_for_target(target, changed_files))

    fixture_proc = None
    fixture_tmpdir = None
    fixture_base_url = None

    if needs_fixture:
        default_base = os.environ.get("BASE_URL", "http://127.0.0.1:18999")
        if not _fixture_session_available(default_base):
            fixture_proc, fixture_base_url, fixture_tmpdir = _start_fixture_server()
            if fixture_proc and fixture_base_url:
                print(f"[fixture-server] started at {fixture_base_url}")
            elif fixture_base_url is None:
                print("[fixture-server] WARNING: could not start fixture server, browserLayout tests may fail")

    try:
        for gate in applicable_gates_for_target(target, changed_files):
            cmd = gate_command(gate, repo_root, target)
            if not cmd:
                details.append(GateDetail(name=gate, status=BLOCKED, command=[], output=f"required gate {gate} 没有可执行命令或依赖缺失。"))
                continue

            # For fixture-dependent gates, inject BASE_URL if fixture server is running
            env_override = None
            if gate in _FIXTURE_GATES and fixture_base_url:
                env_override = {"BASE_URL": fixture_base_url}

            details.append(run_cmd(gate, cmd, repo_root, required=True, env_overrides=env_override))
    finally:
        if fixture_proc:
            _stop_fixture_server(fixture_proc, fixture_tmpdir)
            print(f"[fixture-server] stopped")

    return details


# 04. summary 生成
def build_summary(target: str, change_id: str, started_at: str, details: list[GateDetail]) -> QualitySummary:
    required = {detail.name: detail.status for detail in details}
    status, failures = compute_overall(required)
    return QualitySummary(
        schemaVersion=3,
        status=status,
        target=target,
        changeId=change_id,
        startedAt=started_at,
        finishedAt=utc_now(),
        requiredGates=required,
        blockingFailures=failures,
        warnings=[],
        artifacts={},
        gateDetails=[detail.__dict__ for detail in details],
    )


# 05. CLI
def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic quality gate runner")
    parser.add_argument("--target", required=True, choices=["session-detail", "python-src", "hook-runtime", "harness", "acceptance-contracts", "index"])
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--out", default="tmp/quality",
                        help="Quality artifact directory. Default: tmp/quality")
    parser.add_argument("--changed-files", default=None,
                        help="JSON array of changed file paths, or 'auto' to read from changed-files.jsonl")
    args = parser.parse_args()

    repo_root = Path.cwd()
    validate_target(args.target)
    started_at = utc_now()

    # 解析输出目录：默认 tmp/quality
    out_dir = Path(args.out)

    # 解析 changed files
    changed_files: list[str] | None = None
    if args.changed_files == "auto":
        changed_files = _read_changed_files(repo_root)
    elif args.changed_files:
        import json
        changed_files = json.loads(args.changed_files)

    details = run_target(repo_root, args.target, changed_files)
    summary = build_summary(args.target, args.change_id, started_at, details)
    out = write_quality_summary(repo_root / out_dir, summary, target_specific=True)
    print(f"quality summary: {out}")
    print(f"status: {summary.status}")
    return 0 if summary.status == PASS else 1


def _read_changed_files(repo_root: Path) -> list[str]:
    """从固定路径 tmp/agent_logs/current/changed-files.jsonl 读取文件列表。"""
    changed_file = repo_root / "tmp" / "agent_logs" / "current" / "changed-files.jsonl"
    if not changed_file.exists():
        return []

    session_id_file = repo_root / "tmp" / "agent_logs" / "current" / "session-id.txt"
    session_id = None
    if session_id_file.exists():
        session_id = session_id_file.read_text().strip() or None

    files: list[str] = []
    for line in changed_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            import json
            record = json.loads(line)
            if session_id and record.get("sessionId") != session_id:
                continue
            f = record.get("file") or record.get("file_path")
            if f:
                files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


if __name__ == "__main__":
    raise SystemExit(main())
