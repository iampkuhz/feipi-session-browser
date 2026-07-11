from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONCTL = ROOT / "scripts" / "harness" / "sessionctl.py"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None):
    proc = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"command failed: {cmd}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main_java"], cwd=repo)
    run(["git", "config", "user.email", "doctor-parity@example.invalid"], cwd=repo)
    run(["git", "config", "user.name", "Doctor Parity Test"], cwd=repo)
    (repo / "README.md").write_text("# synthetic\n", encoding="utf-8")
    (repo / ".codex").mkdir()
    (repo / ".codex" / "hooks.json").write_text((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"), encoding="utf-8")
    (repo / ".codex" / "config.toml").write_text((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
    run(["git", "add", "README.md", ".codex/hooks.json", ".codex/config.toml"], cwd=repo)
    run(["git", "commit", "-m", "initial"], cwd=repo)
    return repo


def ctl(repo: Path, *args: str, env: dict[str, str] | None = None, check: bool = True):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return run([sys.executable, str(SESSIONCTL), "--repo-root", str(repo), *args], env=merged, check=check)


def create_bound_run(repo: Path, tmp_path: Path, runtime_root: Path) -> dict:
    env = {"FEIPI_AGENT_RUNTIME_ROOT": str(runtime_root)}
    created = json.loads(
        ctl(
            repo,
            "create",
            "--client",
            "codex",
            "--task-id",
            "task-a",
            "--change-id",
            "support-parallel-primary-sessions",
            "--base-ref",
            "main_java",
            "--allowed-path",
            "docs/a",
            "--worktree-parent",
            str(tmp_path / "worktrees"),
            env=env,
        ).stdout
    )
    ctl(repo, "bind-session", "--run-id", created["runId"], "--session-id", "session-a", "--client", "codex", "--cwd", created["worktreeRoot"], env=env)
    return created


def test_sessionctl_doctor_reports_writable_ready_and_marker_negative(tmp_path: Path):
    repo = git_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    env = {"FEIPI_AGENT_RUNTIME_ROOT": str(runtime_root)}
    record = create_bound_run(repo, tmp_path, runtime_root)

    ok = json.loads(ctl(repo, "doctor", "--run-id", record["runId"], env=env).stdout)
    assert ok["capability"] == "writable-ready"
    assert ok["capabilities"][record["runId"]] == "writable-ready"

    stored = json.loads((runtime_root / "runs" / f"{record['runId']}.json").read_text(encoding="utf-8"))
    Path(stored["hookActivation"]["marker"]["path"]).unlink()
    blocked = ctl(repo, "doctor", "--run-id", record["runId"], env=env, check=False)
    assert blocked.returncode == 2
    data = json.loads(blocked.stdout)
    assert data["capability"] == "blocked"
    assert "hook activation marker missing" in blocked.stdout


def test_sessionctl_doctor_blocks_duplicate_writer_record(tmp_path: Path):
    repo = git_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    env = {"FEIPI_AGENT_RUNTIME_ROOT": str(runtime_root)}
    record = create_bound_run(repo, tmp_path, runtime_root)
    original = json.loads((runtime_root / "runs" / f"{record['runId']}.json").read_text(encoding="utf-8"))
    duplicate = dict(original)
    duplicate["runId"] = "duplicate-run"
    duplicate["writerLease"] = {"leaseId": "lease-duplicate", "holderRunId": "duplicate-run"}
    duplicate["taskId"] = "task-b"
    (runtime_root / "runs" / "duplicate-run.json").write_text(json.dumps(duplicate), encoding="utf-8")
    index = json.loads((runtime_root / "runs" / "index.json").read_text(encoding="utf-8"))
    index["runs"].append("duplicate-run")
    (runtime_root / "runs" / "index.json").write_text(json.dumps(index), encoding="utf-8")

    blocked = ctl(repo, "doctor", env=env, check=False)
    assert blocked.returncode == 2
    assert "same-worktree-writer" in blocked.stdout
    assert '"blocked"' in blocked.stdout


def test_hook_parity_negative_cases_are_detected(tmp_path: Path):
    tmp = tmp_path / "repo-copy"
    shutil.copytree(ROOT, tmp, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "build", ".venv"))

    qoder = tmp / ".qoder" / "settings.json"
    qoder_data = json.loads(qoder.read_text(encoding="utf-8"))
    qoder_data["hooks"]["PreToolUse"] = [entry for entry in qoder_data["hooks"]["PreToolUse"] if entry.get("matcher") != "Bash"]
    qoder.write_text(json.dumps(qoder_data), encoding="utf-8")
    bad_qoder = run([sys.executable, "scripts/quality/check_agent_hook_parity.py"], cwd=tmp, check=False)
    assert bad_qoder.returncode == 1
    assert ".qoder/settings.json PreToolUse matcher=Bash" in bad_qoder.stdout

    qoder.write_text((ROOT / ".qoder" / "settings.json").read_text(encoding="utf-8"), encoding="utf-8")
    codex = tmp / ".codex" / "hooks.json"
    codex_data = json.loads(codex.read_text(encoding="utf-8"))
    codex_data["hooks"]["PreToolUse"][1]["hooks"][0]["command"] = ".codex/hooks/pre_write_guard.sh"
    codex.write_text(json.dumps(codex_data), encoding="utf-8")
    bad_codex = run([sys.executable, "scripts/quality/check_agent_hook_parity.py"], cwd=tmp, check=False)
    assert bad_codex.returncode == 1
    assert ".codex/hooks.json PreToolUse matcher=Write|Edit|MultiEdit|NotebookEdit" in bad_codex.stdout


def test_sessionctl_doctor_reports_read_only_and_legacy_capabilities(tmp_path: Path):
    repo = git_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    env = {"FEIPI_AGENT_RUNTIME_ROOT": str(runtime_root)}

    legacy = json.loads(ctl(repo, "doctor", env=env).stdout)
    assert legacy["capability"] == "legacy-single-writer"

    readonly = json.loads(
        ctl(
            repo,
            "create",
            "--client",
            "qoder",
            "--task-id",
            "readonly-task",
            "--change-id",
            "support-parallel-primary-sessions",
            "--base-ref",
            "main_java",
            "--mode",
            "read-only",
            "--allowed-path",
            "docs/readonly",
            "--worktree-parent",
            str(tmp_path / "worktrees"),
            env=env,
        ).stdout
    )
    checked = json.loads(ctl(repo, "doctor", "--run-id", readonly["runId"], env=env).stdout)
    assert checked["capability"] == "read-only-ready"
    assert checked["capabilities"][readonly["runId"]] == "read-only-ready"
