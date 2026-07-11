import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONCTL = ROOT / "scripts" / "harness" / "sessionctl.py"


def run(cmd, cwd=None, check=True, env=None, input_text=None):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main_java"], cwd=repo)
    run(["git", "config", "user.email", "codex-hooks@example.invalid"], cwd=repo)
    run(["git", "config", "user.name", "Codex Hooks Test"], cwd=repo)
    (repo / "README.md").write_text("# synthetic\n", encoding="utf-8")
    (repo / ".codex").mkdir()
    (repo / ".codex" / "hooks.json").write_text((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"), encoding="utf-8")
    (repo / ".codex" / "config.toml").write_text((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"), encoding="utf-8")
    run(["git", "add", "README.md", ".codex/hooks.json", ".codex/config.toml"], cwd=repo)
    run(["git", "commit", "-m", "initial"], cwd=repo)
    return repo


def ctl(repo: Path, *args, check=True):
    return run([sys.executable, str(SESSIONCTL), "--repo-root", str(repo), *args], cwd=ROOT, check=check)


def test_codex_git_root_command_runs_from_subdir_with_spaces(tmp_path):
    repo = tmp_path / "repo with spaces"
    hook = repo / ".codex" / "hooks" / "session_end.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/usr/bin/env bash\nprintf 'hook:%s\\n' \"$PWD\"\n", encoding="utf-8")
    hook.chmod(0o755)
    run(["git", "init", "-b", "main_java"], cwd=repo)
    subdir = repo / "nested" / "cwd"
    subdir.mkdir(parents=True)

    data = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    command = data["hooks"]["SessionEnd"][0]["hooks"][0]["command"]
    result = run(["sh", "-c", command], cwd=subdir)

    assert result.stdout.startswith("hook:")
    assert str(repo) in result.stdout


def test_sessionctl_bind_session_writes_activation_marker_with_config_hash(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(runtime_root))
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
            "docs",
            "--worktree-parent",
            str(tmp_path / "worktrees"),
        ).stdout
    )
    ctl(
        repo,
        "bind-session",
        "--run-id",
        created["runId"],
        "--session-id",
        "session-a",
        "--client",
        "codex",
        "--cwd",
        created["worktreeRoot"],
    )
    record = json.loads((runtime_root / "runs" / f"{created['runId']}.json").read_text(encoding="utf-8"))
    marker_path = Path(record["hookActivation"]["marker"]["path"])
    marker = json.loads(marker_path.read_text(encoding="utf-8"))

    assert marker["sessionId"] == "session-a"
    assert marker["configHash"][".codex/hooks.json"]
    assert marker["configHash"][".codex/config.toml"]
    assert ctl(repo, "doctor", "--run-id", created["runId"]).returncode == 0


def test_unbound_codex_write_is_blocked_read_only():
    payload = json.dumps({"client": "codex", "session_id": "direct", "tool_name": "Write", "tool_input": {"file_path": "docs/direct.md"}})
    env = os.environ.copy()
    env.pop("FEIPI_RUN_ID", None)
    env.pop("FEIPI_LEGACY_SINGLE_WRITER", None)
    env["FEIPI_AGENT_CLIENT"] = "codex"
    result = run([sys.executable, "-m", "scripts.claude_hooks.main", "pre-write"], cwd=ROOT, env=env, input_text=payload, check=False)

    assert result.returncode == 2
    assert "unbound Codex session is read-only" in result.stderr


def test_wrong_worktree_resume_blocks_write(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(runtime_root))
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
            "docs",
            "--worktree-parent",
            str(tmp_path / "worktrees"),
        ).stdout
    )
    worktree = Path(created["worktreeRoot"])
    ctl(repo, "bind-session", "--run-id", created["runId"], "--session-id", "session-a", "--client", "codex", "--cwd", str(worktree))
    payload = json.dumps({"client": "codex", "session_id": "session-a", "run_id": created["runId"], "cwd": str(repo), "tool_name": "Write", "tool_input": {"file_path": "docs/x.md"}})
    env = os.environ.copy()
    env["FEIPI_AGENT_RUNTIME_ROOT"] = str(runtime_root)
    env["FEIPI_AGENT_CLIENT"] = "codex"
    env["PYTHONPATH"] = str(ROOT)
    result = run([sys.executable, "-m", "scripts.claude_hooks.main", "pre-write"], cwd=repo, env=env, input_text=payload, check=False)

    assert result.returncode == 2
    assert "cwd realpath does not match run worktree root" in result.stderr


def test_unbound_qoder_write_is_blocked_read_only_unbound():
    payload = json.dumps({"client": "qoder", "session_id": "direct-qoder", "tool_name": "Write", "tool_input": {"file_path": "docs/direct-qoder.md"}})
    env = os.environ.copy()
    env.pop("FEIPI_RUN_ID", None)
    env.pop("FEIPI_LEGACY_SINGLE_WRITER", None)
    env.pop("FEIPI_PRIMARY_SESSION_MODE", None)
    env["FEIPI_AGENT_CLIENT"] = "qoder"
    result = run([sys.executable, "-m", "scripts.claude_hooks.main", "pre-write"], cwd=ROOT, env=env, input_text=payload, check=False)

    assert result.returncode == 2
    assert "read-only-unbound" in result.stderr
    assert "managed-worktree" in result.stderr


def test_explicit_legacy_single_writer_warns_but_does_not_claim_multi_primary():
    payload = json.dumps({"client": "codex", "session_id": "legacy-direct", "tool_name": "Write", "tool_input": {"file_path": "docs/legacy-direct.md"}})
    env = os.environ.copy()
    env.pop("FEIPI_RUN_ID", None)
    env["FEIPI_AGENT_CLIENT"] = "codex"
    env["FEIPI_PRIMARY_SESSION_MODE"] = "read-only-ready"
    result = run([sys.executable, "-m", "scripts.claude_hooks.main", "pre-write"], cwd=ROOT, env=env, input_text=payload, check=False)

    assert result.returncode == 0
    events = ROOT / "tmp" / "agent_logs" / "codex" / "legacy-direct" / "main" / "hook-events.jsonl"
    assert "read-only-ready mode is explicit compatibility only" in events.read_text(encoding="utf-8")


def test_legacy_single_writer_blocks_when_managed_writer_exists(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(runtime_root))
    created = json.loads(
        ctl(
            repo,
            "create",
            "--client",
            "codex",
            "--task-id",
            "managed-task",
            "--change-id",
            "support-parallel-primary-sessions",
            "--base-ref",
            "main_java",
            "--allowed-path",
            "docs/managed",
            "--worktree-parent",
            str(tmp_path / "worktrees"),
        ).stdout
    )
    payload = json.dumps({"client": "codex", "session_id": "legacy-direct", "cwd": str(repo), "tool_name": "Write", "tool_input": {"file_path": "docs/legacy.md"}})
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["FEIPI_AGENT_RUNTIME_ROOT"] = str(runtime_root)
    env["FEIPI_AGENT_CLIENT"] = "codex"
    env["FEIPI_PRIMARY_SESSION_MODE"] = "read-only-ready"
    result = run([sys.executable, "-m", "scripts.claude_hooks.main", "pre-write"], cwd=repo, env=env, input_text=payload, check=False)

    assert created["primarySessionMode"] == "managed-worktree"
    assert result.returncode == 2
    assert "read-only-ready blocked by active managed writable run" in result.stderr
