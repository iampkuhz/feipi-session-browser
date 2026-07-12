import argparse
import json
import subprocess
from pathlib import Path

import pytest
from scripts.harness import complete_change, sessionctl, stop_entry
from scripts.harness.primary_session import resolve_runtime_root


@pytest.fixture(autouse=True)
def isolated_runtime_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FEIPI_AGENT_RUNTIME_ROOT", str(tmp_path / "runtime"))


def run(cmd, cwd, check=True):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init", "-b", "main_java"], repo)
    run(["git", "config", "user.email", "complete@example.invalid"], repo)
    run(["git", "config", "user.name", "Complete Test"], repo)
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    (repo / "obsolete.txt").write_text("obsolete\n", encoding="utf-8")
    run(["git", "add", "README.md", "obsolete.txt"], repo)
    run(["git", "commit", "-m", "initial"], repo)
    (repo / ".git" / "info" / "exclude").write_text(
        "tmp/agent_logs/\ntmp/quality/\n", encoding="utf-8"
    )
    return repo


def linked_run(tmp_path, *, dirty_before_bootstrap=False, detached=False):
    primary = git_repo(tmp_path)
    linked = tmp_path / "linked"
    branch_args = ["--detach"] if detached else ["-b", "codex/change"]
    run(["git", "worktree", "add", *branch_args, str(linked), "HEAD"], primary)
    if dirty_before_bootstrap:
        (linked / "before.txt").write_text("before\n", encoding="utf-8")
    record = sessionctl.cmd_bootstrap(
        argparse.Namespace(
            client="codex",
            session_id="session-complete",
            cwd=str(linked),
            hook_event="SessionStart",
            checkout_creator="codex",
            run_id=None,
            worktree_id=None,
            parent_run_id=None,
            repo_root=str(linked),
        )
    )
    assert record == 0
    registry = sessionctl.Registry(linked)
    with registry.locked():
        records = [
            item
            for item in registry.all_runs()
            if item["client"] == "codex"
            and item["sessionId"] == "session-complete"
            and item["checkoutRoot"] == str(linked.resolve())
        ]
    assert len(records) == 1
    return primary, linked, records[0]


def install_fake_stop_pass(monkeypatch, calls):
    def fake_run_stop(client, payload, *, handoff_on_failure=False, adapter_mode="hook"):
        assert adapter_mode == "cli"
        calls.append(payload["runId"])
        checkout = Path(payload["cwd"])
        registry = sessionctl.Registry(checkout)
        with registry.locked():
            record = registry.load_run(payload["runId"])
        facts = stop_entry.collect_git_evidence(checkout, record)
        summary = (
            checkout
            / "tmp"
            / "agent_logs"
            / client
            / payload["sessionId"]
            / "runs"
            / payload["runId"]
            / "main"
            / "stop-check-summary.json"
        )
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(json.dumps({"status": "PASS"}) + "\n", encoding="utf-8")
        sessionctl.record_stop_result(
            checkout,
            payload["runId"],
            stop_exit=0,
            summary_status="PASS",
            validated_facts=facts,
            handoff_on_failure=handoff_on_failure,
        )
        return 0

    monkeypatch.setattr(stop_entry, "run_stop", fake_run_stop)


def invoke(linked, record, *files):
    args = [
        "--repo-root",
        str(linked),
        "--run-id",
        record["runId"],
        "--message",
        "chore: complete change",
    ]
    for path in files:
        args.extend(["--file", path])
    return complete_change.main(args)


def test_complete_change_commits_revalidates_and_ff_integrates(tmp_path, monkeypatch, capsys):
    primary, linked, record = linked_run(tmp_path)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    (linked / "README.md").write_text("updated\n", encoding="utf-8")
    (linked / "added.txt").write_text("added\n", encoding="utf-8")
    (linked / "obsolete.txt").unlink()

    result = invoke(linked, record, "README.md", "added.txt", "obsolete.txt")

    assert result == 0
    assert calls == [record["runId"], record["runId"]]
    assert run(["git", "log", "-1", "--format=%s"], primary).stdout.strip() == (
        "chore: complete change"
    )
    assert (
        run(["git", "rev-parse", "HEAD"], primary).stdout
        == run(["git", "rev-parse", "HEAD"], linked).stdout
    )
    registry = sessionctl.Registry(linked)
    with registry.locked():
        latest = registry.load_run(record["runId"])
    assert latest["status"] == "INTEGRATED"
    summary = json.loads(Path(latest["integrationSummary"]).read_text(encoding="utf-8"))
    assert summary["pushed"] is False
    assert resolve_runtime_root(linked) in Path(latest["integrationSummary"]).parents
    capsys.readouterr()


@pytest.mark.parametrize(
    ("setup", "files", "reason"),
    [
        (
            lambda linked: (linked / "actual.txt").write_text("x\n", encoding="utf-8"),
            ["other.txt"],
            "scope",
        ),
        (
            lambda linked: (
                (linked / "staged.txt").write_text("x\n", encoding="utf-8"),
                run(["git", "add", "staged.txt"], linked),
            ),
            ["staged.txt"],
            "staged",
        ),
    ],
)
def test_complete_change_rejects_unattributed_or_prestaged_changes(
    tmp_path, monkeypatch, capsys, setup, files, reason
):
    primary, linked, record = linked_run(tmp_path)
    before = run(["git", "rev-parse", "HEAD"], linked).stdout
    setup(linked)
    install_fake_stop_pass(monkeypatch, [])

    assert invoke(linked, record, *files) == 2
    assert run(["git", "rev-parse", "HEAD"], linked).stdout == before
    assert run(["git", "rev-parse", "HEAD"], primary).stdout == before
    assert reason in capsys.readouterr().err


def test_complete_change_rejects_initial_or_primary_dirty_checkout(tmp_path, monkeypatch, capsys):
    primary, linked, record = linked_run(tmp_path, dirty_before_bootstrap=True)
    (linked / "change.txt").write_text("change\n", encoding="utf-8")
    install_fake_stop_pass(monkeypatch, [])

    assert invoke(linked, record, "before.txt", "change.txt") == 2
    assert "initial dirty" in capsys.readouterr().err

    other_root = tmp_path / "other"
    other_root.mkdir()
    primary, linked, record = linked_run(other_root)
    (linked / "change.txt").write_text("change\n", encoding="utf-8")
    (primary / "primary.txt").write_text("dirty\n", encoding="utf-8")
    assert invoke(linked, record, "change.txt") == 2
    assert "primary checkout dirty" in capsys.readouterr().err


def test_complete_change_does_not_commit_when_first_stop_fails(tmp_path, monkeypatch):
    primary, linked, record = linked_run(tmp_path)
    (linked / "change.txt").write_text("change\n", encoding="utf-8")
    before = run(["git", "rev-parse", "HEAD"], linked).stdout
    monkeypatch.setattr(complete_change, "_run_stop", lambda _repo, _run_id: 2)

    assert invoke(linked, record, "change.txt") == 2
    assert run(["git", "rev-parse", "HEAD"], linked).stdout == before
    assert run(["git", "rev-parse", "HEAD"], primary).stdout == before


def test_complete_change_rejects_detached_and_forbidden_paths(tmp_path, monkeypatch, capsys):
    primary, linked, record = linked_run(tmp_path, detached=True)
    (linked / "change.txt").write_text("change\n", encoding="utf-8")
    install_fake_stop_pass(monkeypatch, [])
    assert invoke(linked, record, "change.txt") == 2
    assert "named branch" in capsys.readouterr().err

    other_root = tmp_path / "other"
    other_root.mkdir()
    primary, linked, record = linked_run(other_root)
    (linked / "data").mkdir()
    (linked / "data" / "private.txt").write_text("private\n", encoding="utf-8")
    assert invoke(linked, record, "data/private.txt") == 2
    assert "forbidden files" in capsys.readouterr().err
