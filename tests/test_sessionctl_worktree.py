import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONCTL = ROOT / "scripts" / "harness" / "sessionctl.py"

from scripts.harness.primary_session import resolve_runtime_root


def run(cmd, cwd=None, check=True, env=None):
    result = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main_java"], cwd=repo)
    run(["git", "config", "user.email", "sessionctl@example.invalid"], cwd=repo)
    run(["git", "config", "user.name", "Sessionctl Test"], cwd=repo)
    (repo / "README.md").write_text("# synthetic\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=repo)
    run(["git", "commit", "-m", "initial"], cwd=repo)
    return repo


def ctl(repo, *args, check=True):
    return run([sys.executable, str(SESSIONCTL), "--repo-root", str(repo), *args], cwd=ROOT, check=check)


def create(repo, tmp_path, task, client="codex", allowed="docs"):
    parent = tmp_path / "worktrees"
    result = ctl(
        repo,
        "create",
        "--client",
        client,
        "--task-id",
        task,
        "--change-id",
        "support-parallel-primary-sessions",
        "--base-ref",
        "main_java",
        "--allowed-path",
        allowed,
        "--worktree-parent",
        str(parent),
    )
    return json.loads(result.stdout)


def test_two_runs_create_two_real_git_worktrees_and_list_status(tmp_path):
    repo = git_repo(tmp_path)
    first = create(repo, tmp_path, "task-a", client="codex", allowed="docs/a")
    second = create(repo, tmp_path, "task-b", client="qoder", allowed="docs/b")

    assert first["runId"] != second["runId"]
    assert Path(first["worktreeRoot"]).exists()
    assert Path(second["worktreeRoot"]).exists()
    assert run(["git", "-C", first["worktreeRoot"], "branch", "--show-current"]).stdout.strip() == first["branch"]

    listed = ctl(repo, "list", "--json")
    ids = {item["runId"] for item in json.loads(listed.stdout)}
    assert {first["runId"], second["runId"]} <= ids

    status = json.loads(ctl(repo, "status", "--run-id", first["runId"]).stdout)
    assert status["checks"]["branchMatches"] is True
    assert status["checks"]["dirty"] is False


def test_same_branch_conflict_is_blocked_before_worktree_create(tmp_path):
    repo = git_repo(tmp_path)
    first = create(repo, tmp_path, "task-a", allowed="docs/a")
    result = ctl(
        repo,
        "create",
        "--client",
        "codex",
        "--task-id",
        "task-b",
        "--change-id",
        "support-parallel-primary-sessions",
        "--base-ref",
        "main_java",
        "--allowed-path",
        "docs/b",
        "--branch",
        first["branch"],
        "--worktree-parent",
        str(tmp_path / "worktrees"),
        check=False,
    )
    assert result.returncode == 2
    assert "branch already exists" in result.stderr


def test_same_worktree_second_writer_conflict_is_blocked(tmp_path):
    repo = git_repo(tmp_path)
    first = create(repo, tmp_path, "task-a", allowed="docs/a")
    result = ctl(
        repo,
        "create",
        "--client",
        "qoder",
        "--task-id",
        "task-b",
        "--change-id",
        "support-parallel-primary-sessions",
        "--base-ref",
        "main_java",
        "--allowed-path",
        "docs/b",
        "--worktree-root",
        first["worktreeRoot"],
        check=False,
    )
    assert result.returncode == 2
    assert "worktree path already owned" in result.stderr


def test_create_failure_rolls_back_empty_registry_record(tmp_path):
    repo = git_repo(tmp_path)
    bad_parent = tmp_path / "parent-file"
    bad_parent.write_text("not a directory", encoding="utf-8")
    result = ctl(
        repo,
        "create",
        "--client",
        "codex",
        "--task-id",
        "bad-task",
        "--change-id",
        "support-parallel-primary-sessions",
        "--base-ref",
        "main_java",
        "--allowed-path",
        "docs/bad",
        "--worktree-parent",
        str(bad_parent),
        check=False,
    )
    assert result.returncode == 2
    listed = json.loads(ctl(repo, "list", "--json").stdout)
    assert listed == []


def test_dirty_worktree_cleanup_is_refused_and_dry_run_is_non_destructive(tmp_path):
    repo = git_repo(tmp_path)
    record = create(repo, tmp_path, "task-a", allowed="docs/a")
    dry_run = json.loads(ctl(repo, "cleanup", "--run-id", record["runId"]).stdout)
    assert dry_run["status"] == "dry-run"
    assert Path(record["worktreeRoot"]).exists()

    (Path(record["worktreeRoot"]) / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    result = ctl(repo, "cleanup", "--run-id", record["runId"], "--execute", check=False)
    assert result.returncode == 2
    assert "dirty worktree" in result.stderr
    assert Path(record["worktreeRoot"]).exists()


def test_bind_session_rejects_wrong_cwd_and_allows_idempotent_resume(tmp_path):
    repo = git_repo(tmp_path)
    record = create(repo, tmp_path, "task-a", allowed="docs/a")

    wrong = ctl(
        repo,
        "bind-session",
        "--run-id",
        record["runId"],
        "--session-id",
        "session-a",
        "--client",
        "codex",
        "--cwd",
        str(repo),
        check=False,
    )
    assert wrong.returncode == 2
    assert "cwd does not match" in wrong.stderr

    bound = json.loads(
        ctl(
            repo,
            "bind-session",
            "--run-id",
            record["runId"],
            "--session-id",
            "session-a",
            "--client",
            "codex",
            "--cwd",
            record["worktreeRoot"],
        ).stdout
    )
    assert bound["status"] == "running"

    rebound = json.loads(
        ctl(
            repo,
            "bind-session",
            "--run-id",
            record["runId"],
            "--session-id",
            "session-a",
            "--client",
            "codex",
            "--cwd",
            record["worktreeRoot"],
        ).stdout
    )
    assert rebound["sessionId"] == "session-a"

    different = ctl(
        repo,
        "bind-session",
        "--run-id",
        record["runId"],
        "--session-id",
        "session-b",
        "--client",
        "codex",
        "--cwd",
        record["worktreeRoot"],
        check=False,
    )
    assert different.returncode == 2
    assert "different active primary session" in different.stderr


def test_start_print_command_and_handoff_do_not_start_real_client(tmp_path):
    repo = git_repo(tmp_path)
    record = create(repo, tmp_path, "task-a", allowed="docs/a")
    printed = ctl(repo, "start", "--run-id", record["runId"], "--print-command").stdout
    assert "FEIPI_RUN_ID=" in printed
    assert "<client-command>" in printed

    handoff = json.loads(ctl(repo, "handoff", "--run-id", record["runId"]).stdout)
    assert handoff["branch"] == record["branch"]
    assert handoff["changeId"] == "support-parallel-primary-sessions"


def test_registry_concurrent_writes_keep_valid_json(tmp_path):
    repo = git_repo(tmp_path)

    def make(i):
        return create(repo, tmp_path, f"task-{i}", client="codex", allowed=f"docs/{i}")["runId"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        run_ids = list(pool.map(make, range(4)))
    listed = json.loads(ctl(repo, "list", "--json").stdout)
    assert set(run_ids) <= {item["runId"] for item in listed}

def test_handoff_includes_rollout_fields(tmp_path):
    repo = git_repo(tmp_path)
    record = create(repo, tmp_path, "task-rollout", allowed="docs/rollout")
    handoff = json.loads(ctl(repo, "handoff", "--run-id", record["runId"]).stdout)

    assert handoff["runId"] == record["runId"]
    assert handoff["taskId"] == "task-rollout"
    assert handoff["client"] == "codex"
    assert handoff["worktreeRoot"] == record["worktreeRoot"]
    assert handoff["branch"] == record["branch"]
    assert handoff["baseCommit"] == record["baseCommit"]
    assert handoff["primarySessionMode"] == "managed-worktree"
    assert handoff["requiredTargetSummary"]["allowedPaths"] == ["docs/rollout"]
    assert "runRecord" in handoff["artifactPaths"]
    assert "blockingFailures" in handoff
    assert "writeScopeOverlap" in handoff["mergeRisk"]
    assert any("commit/push/merge manually" in step for step in handoff["manualNextSteps"])


def test_cleanup_dry_run_documents_rollback_without_deleting_worktree_or_branch(tmp_path):
    repo = git_repo(tmp_path)
    record = create(repo, tmp_path, "task-rollback", allowed="docs/rollback")
    branch = record["branch"]
    dry_run = json.loads(ctl(repo, "cleanup", "--run-id", record["runId"]).stdout)

    assert dry_run["status"] == "dry-run"
    assert dry_run["actions"]["dryRun"] is True
    assert Path(record["worktreeRoot"]).exists()
    assert run(["git", "-C", str(repo), "show-ref", "--verify", f"refs/heads/{branch}"], check=False).returncode == 0


def test_stop_runs_unified_stop_and_writes_artifacts(tmp_path):
    repo = git_repo(tmp_path)
    record = create(repo, tmp_path, "task-stop", allowed="docs/stop")
    ctl(
        repo,
        "bind-session",
        "--run-id",
        record["runId"],
        "--session-id",
        "session-stop",
        "--client",
        "codex",
        "--cwd",
        record["worktreeRoot"],
    )

    stopped = json.loads(ctl(repo, "stop", "--run-id", record["runId"]).stdout)

    assert stopped["status"] == "completed"
    assert stopped["stopExitCode"] == 0
    run_root = (
        Path(record["worktreeRoot"])
        / "tmp"
        / "agent_logs"
        / "codex"
        / "session-stop"
        / "runs"
        / record["runId"]
        / "main"
    )
    assert (run_root / "stop-check-summary.json").is_file()
    runtime_report = (
        Path(record["worktreeRoot"])
        / "tmp"
        / "quality"
        / "codex"
        / "session-stop"
        / "runs"
        / record["runId"]
        / "main"
        / "support-parallel-primary-sessions"
        / "runtime-report.json"
    )
    assert runtime_report.is_file()
    latest = json.loads(
        (
            resolve_runtime_root(repo)
            / "runs"
            / f"{record['runId']}.json"
        ).read_text(encoding="utf-8")
    )
    assert latest["status"] == "completed"
