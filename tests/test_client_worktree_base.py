from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.agent_runtime.session import contract as primary_session
from scripts.agent_runtime.session import lifecycle as sessionctl
from scripts.harness import launch_codex_worktree

ROOT = Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def synthetic_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Worktree Base Test")
    git(repo, "config", "user.email", "worktree-base@example.invalid")
    (repo / "README.md").write_text("old default\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "old default")
    old_head = git(repo, "rev-parse", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/main", old_head)
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(repo, "switch", "-c", "main_java")
    (repo / "README.md").write_text("current local branch\n", encoding="utf-8")
    git(repo, "commit", "-am", "current local branch")
    return repo, old_head, git(repo, "rev-parse", "HEAD")


def test_claude_repository_setting_uses_current_head() -> None:
    settings = json.loads((ROOT / ".claude/settings.json").read_text(encoding="utf-8"))

    assert settings["worktree"]["baseRef"] == "head"
    assert settings["agent"] == "qwen-main-default"
    assert settings["hooks"]


def test_codex_cli_launcher_uses_primary_head_not_origin_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, old_head, current_head = synthetic_repo(tmp_path)
    worktree_root = tmp_path / "external-worktrees"
    client = "codex-cli"

    result = launch_codex_worktree.main(
        [
            "--client",
            client,
            "--name",
            client,
            "--repo-root",
            str(repo),
            "--worktree-root",
            str(worktree_root),
            "--no-launch",
            "--",
            "--model",
            "gpt-test",
        ]
    )

    assert result == 0
    evidence = json.loads(capsys.readouterr().out)
    checkout = worktree_root / client
    assert evidence["status"] == "READY"
    assert evidence["primarySnapshot"]["branch"] == "main_java"
    assert evidence["primarySnapshot"]["head_commit"] == current_head
    assert evidence["command"][:2] == ["codex", "-C"]
    assert git(checkout, "rev-parse", "HEAD") == current_head
    assert git(checkout, "rev-parse", "HEAD") != old_head
    assert git(checkout, "branch", "--show-current") == f"codex/worktree-{client}"
    assert evidence["command"][-2:] == ["--model", "gpt-test"]


@pytest.mark.parametrize("override", ("-C", "-C/tmp/other", "--cd", "--cd=/tmp/other"))
def test_codex_launcher_rejects_checkout_override(
    capsys: pytest.CaptureFixture[str], override: str
) -> None:
    result = launch_codex_worktree.main(
        [
            "--client",
            "codex-cli",
            "--name",
            "override",
            "--no-launch",
            "--",
            override,
        ]
    )

    assert result == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "BLOCKED"
    assert error["code"] == "CHECKOUT_OVERRIDE_FORBIDDEN"


def test_new_codex_run_blocks_wrong_base_but_resume_reuses_registered_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, old_head, current_head = synthetic_repo(tmp_path)
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))
    matching = tmp_path / "matching"
    mismatch = tmp_path / "mismatch"
    git(repo, "worktree", "add", "-b", "codex/matching", str(matching), current_head)
    git(repo, "worktree", "add", "-b", "codex/mismatch", str(mismatch), old_head)

    record = sessionctl.bootstrap_session(
        client="codex",
        session_id="matching-session",
        cwd=matching,
        hook_event="SessionStart",
        checkout_creator="codex",
    )

    assert record["baseCommit"] == current_head
    assert record["targetBranch"] == "main_java"
    assert record["worktreeBase"] == {
        "policy": "primary-head",
        "expectedBranch": "main_java",
        "expectedHead": current_head,
        "actualHead": current_head,
        "matched": True,
    }

    (matching / "work.txt").write_text("session commit\n", encoding="utf-8")
    git(matching, "add", "work.txt")
    git(matching, "commit", "-m", "session commit")
    (repo / "primary.txt").write_text("primary advanced\n", encoding="utf-8")
    git(repo, "add", "primary.txt")
    git(repo, "commit", "-m", "primary advanced")

    resumed = sessionctl.bootstrap_session(
        client="codex",
        session_id="matching-session",
        cwd=matching,
        hook_event="PreToolUse",
        checkout_creator="codex",
    )

    assert resumed["runId"] == record["runId"]
    assert resumed["baseCommit"] == current_head
    with pytest.raises(sessionctl.SessionctlError, match="WORKTREE_BASE_MISMATCH") as blocked:
        sessionctl.bootstrap_session(
            client="codex",
            session_id="mismatch-session",
            cwd=mismatch,
            hook_event="SessionStart",
            checkout_creator="codex",
        )
    message = str(blocked.value)
    assert old_head in message
    assert git(mismatch, "rev-parse", "HEAD") == old_head
    assert not [
        item
        for item in sessionctl.Registry(repo).all_runs()
        if item["sessionId"] == "mismatch-session"
    ]


def test_primary_detached_and_snapshot_race_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _, _ = synthetic_repo(tmp_path)
    git(repo, "switch", "--detach")
    with pytest.raises(
        primary_session.PrimarySessionValidationError,
        match="PRIMARY_HEAD_DETACHED",
    ):
        primary_session.capture_primary_head_snapshot(repo)

    git(repo, "switch", "main_java")
    original_git_output = primary_session.git_output
    head_reads = 0

    def racing_git_output(repo_root: Path, *args: str) -> str:
        nonlocal head_reads
        value = original_git_output(repo_root, *args)
        if args == ("rev-parse", "HEAD"):
            head_reads += 1
            if head_reads == 2:
                return "f" * 40
        return value

    monkeypatch.setattr(primary_session, "git_output", racing_git_output)
    with pytest.raises(
        primary_session.PrimarySessionValidationError,
        match="PRIMARY_HEAD_RACE",
    ):
        primary_session.capture_primary_head_snapshot(repo)
