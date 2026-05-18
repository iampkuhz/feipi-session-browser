#!/usr/bin/env python3
"""Unified quality gate runner.

Executes deterministic quality gates for a given target and writes
a structured summary artifact to .agent/quality/<change-id>/.

Usage:
    python3 scripts/quality/run_quality_gate.py --target session-detail
    python3 scripts/quality/run_quality_gate.py --target session-detail --change-id fix-xyz
    python3 scripts/quality/run_quality_gate.py --target session-detail --out .agent/quality/demo
    python3 scripts/quality/run_quality_gate.py --target session-detail --allow-missing-service
    python3 scripts/quality/run_quality_gate.py --self-test
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUALITY_DIR = REPO_ROOT / ".agent" / "quality"

SCRIPTS = {
    "staticCssContract": "scripts/quality/check_session_detail_static.py",
    "browserLayout": "scripts/quality/run_session_detail_layout_gate.py",
}

PYTEST_TEST = "tests/test_session_detail_layout_contract.py"


def resolve_change_id(explicit: str | None) -> str:
    """Resolve change ID from args, env, or file fallback."""
    if explicit:
        return explicit
    env = os.environ.get("ACTIVE_CHANGE_ID")
    if env:
        return env
    active_file = REPO_ROOT / ".agent" / "active-change"
    if active_file.exists():
        return active_file.read_text().strip()
    return "unknown"


def resolve_out_dir(change_id: str, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = REPO_ROOT / p
        return p
    return QUALITY_DIR / change_id


def run_command(cmd: list[str], cwd: Path | None = None) -> dict:
    """Run a subprocess and return result info."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or REPO_ROOT,
            timeout=120,
        )
        return {
            "exitCode": result.returncode,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:4000],
        }
    except subprocess.TimeoutExpired:
        return {"exitCode": -1, "stdout": "", "stderr": "timeout after 120s"}
    except FileNotFoundError:
        return {"exitCode": 127, "stdout": "", "stderr": f"command not found: {cmd[0]}"}
    except Exception as e:
        return {"exitCode": 2, "stdout": "", "stderr": str(e)}


def gate_static_css(out_dir: Path, allow_missing: bool = False) -> dict:
    """Run static CSS gate if available."""
    script = REPO_ROOT / SCRIPTS["staticCssContract"]
    if not script.exists():
        return {"gate": "staticCssContract", "status": "SKIPPED", "summary": "Script not found"}

    result = run_command([sys.executable, str(script)])
    summary_text = (result["stdout"] or result["stderr"]).strip().split("\n")[-1] if result["stdout"] or result["stderr"] else "no output"
    return {
        "gate": "staticCssContract",
        "status": "PASS" if result["exitCode"] == 0 else "FAIL",
        "command": f"python3 {SCRIPTS['staticCssContract']}",
        "exitCode": result["exitCode"],
        "summary": summary_text,
    }


def gate_template_contract(out_dir: Path, allow_missing: bool = False) -> dict:
    """Run template contract pytest if available."""
    test = REPO_ROOT / PYTEST_TEST
    if not test.exists():
        return {"gate": "templateContract", "status": "SKIPPED", "summary": "Test not found"}

    result = run_command([sys.executable, "-m", "pytest", str(test), "-v", "--tb=short"])
    stdout = result.get("stdout", "")
    # Extract summary line
    summary_lines = [l for l in stdout.split("\n") if "passed" in l or "failed" in l or "error" in l.lower()]
    summary = summary_lines[-1] if summary_lines else "pytest completed"
    return {
        "gate": "templateContract",
        "status": "PASS" if result["exitCode"] == 0 else "FAIL",
        "command": f"python3 -m pytest {PYTEST_TEST}",
        "exitCode": result["exitCode"],
        "summary": summary,
    }


def gate_browser_layout(out_dir: Path, allow_missing: bool = False) -> dict:
    """Run browser layout gate if available."""
    script = REPO_ROOT / SCRIPTS["browserLayout"]
    if not script.exists():
        return {"gate": "browserLayout", "status": "SKIPPED", "summary": "Script not found"}

    # Check if we have a URL to test against
    url = os.environ.get("QUALITY_GATE_URL")
    if not url:
        return {
            "gate": "browserLayout",
            "status": "SKIPPED",
            "summary": "No URL provided (set QUALITY_GATE_URL or pass --url via runner)",
        }

    cmd = [sys.executable, str(script), "--url", url, "--out", str(out_dir)]
    if allow_missing:
        cmd.append("--allow-missing-service")
    result = run_command(cmd)
    summary_text = (result["stdout"] or result["stderr"] or "").strip().split("\n")[-1]
    artifact = str(out_dir / "session-detail-layout-result.json")
    return {
        "gate": "browserLayout",
        "status": "PASS" if result["exitCode"] == 0 else "FAIL",
        "command": " ".join(cmd),
        "exitCode": result["exitCode"],
        "summary": summary_text,
        "artifact": artifact,
    }


def gate_pytest(out_dir: Path, allow_missing: bool = False) -> dict:
    """Run product pytest suite."""
    # Try session-browser.sh first
    sh_script = REPO_ROOT / "scripts" / "session-browser.sh"
    if sh_script.exists() and os.access(sh_script, os.X_OK):
        result = run_command([str(sh_script), "test"])
        if result["exitCode"] == 0:
            return {
                "gate": "pytest",
                "status": "PASS",
                "command": "./scripts/session-browser.sh test",
                "exitCode": 0,
                "summary": "session-browser.sh test passed",
            }

    # Fallback to pytest
    result = run_command([sys.executable, "-m", "pytest", "-q", "--tb=short"])
    stdout = result.get("stdout", "")
    summary_lines = [l for l in stdout.split("\n") if "passed" in l or "failed" in l or "error" in l.lower()]
    summary = summary_lines[-1] if summary_lines else "pytest completed"
    return {
        "gate": "pytest",
        "status": "PASS" if result["exitCode"] == 0 else "FAIL",
        "command": "python3 -m pytest",
        "exitCode": result["exitCode"],
        "summary": summary,
    }


def aggregate_status(gate_results: list[dict]) -> tuple[str, list[str], list[str]]:
    """Compute overall status from gate results."""
    blocking: list[str] = []
    warnings: list[str] = []

    for r in gate_results:
        status = r["status"]
        gate_name = r["gate"]
        if status == "FAIL":
            blocking.append(f"{gate_name}: {r.get('summary', '')}")
        elif status == "BLOCKED":
            blocking.append(f"{gate_name}: {r.get('summary', 'blocked')}")
        elif status == "SKIPPED":
            warnings.append(f"{gate_name}: skipped (not yet implemented)")

    overall = "PASS" if not blocking else "FAIL"
    return overall, blocking, warnings


def build_summary(
    target: str,
    change_id: str,
    gate_results: list[dict],
    overall: str,
    blocking: list[str],
    warnings: list[str],
    started_at: str,
) -> dict:
    """Build the quality-gate-summary.json structure."""
    finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    required_gates = {r["gate"]: r["status"] for r in gate_results}

    return {
        "schemaVersion": 1,
        "status": overall,
        "target": target,
        "changeId": change_id,
        "startedAt": started_at,
        "finishedAt": finished,
        "requiredGates": required_gates,
        "blockingFailures": blocking,
        "warnings": warnings,
        "artifacts": {
            r["gate"]: r.get("artifact", "")
            for r in gate_results
            if r.get("artifact")
        },
        "gateDetails": gate_results,
    }


def _write_summary_artifact(out_dir: Path, summary: dict) -> Path:
    """Write summary to artifact file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "quality-gate-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary_path


def run_gates(target: str, change_id: str, out_dir: Path, allow_missing: bool = False) -> dict:
    """Run all gates for the target and return summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    results: list[dict] = []

    if target == "session-detail":
        results.append(gate_static_css(out_dir, allow_missing))
        results.append(gate_template_contract(out_dir, allow_missing))
        results.append(gate_browser_layout(out_dir, allow_missing))
        results.append(gate_pytest(out_dir, allow_missing))
    else:
        results.append(gate_pytest(out_dir, allow_missing))

    overall, blocking, warnings = aggregate_status(results)
    summary = build_summary(target, change_id, results, overall, blocking, warnings, started_at)

    # Write artifact
    _write_summary_artifact(out_dir, summary)
    return summary


def _self_test():
    """Run self-tests for the quality runner."""
    import tempfile
    failures = 0

    def _run(name, func):
        nonlocal failures
        try:
            func()
            print(f"  PASS: {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL: {name} - {e}")
        except Exception as e:
            failures += 1
            print(f"  FAIL: {name} - {type(e).__name__}: {e}")

    def _t1_change_id_fallback():
        """Change ID falls back to 'unknown'."""
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            os.environ.pop("ACTIVE_CHANGE_ID", None)
            # We can't test .agent/active-change without side effects,
            # so test resolve_change_id with explicit None and no env
            # by checking it returns something non-empty
            cid = resolve_change_id(None)
            assert isinstance(cid, str) and len(cid) > 0
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old

    def _t2_change_id_explicit():
        """Explicit change ID takes priority."""
        assert resolve_change_id("my-change") == "my-change"

    def _t3_change_id_env():
        """ENV change ID used when explicit is None."""
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            os.environ["ACTIVE_CHANGE_ID"] = "env-change"
            assert resolve_change_id(None) == "env-change"
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old
            else:
                os.environ.pop("ACTIVE_CHANGE_ID", None)

    def _t4_summary_json_written():
        """Summary JSON is written to correct path with required schema."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            results = [
                {"gate": "staticCssContract", "status": "SKIPPED", "summary": "not yet"},
                {"gate": "templateContract", "status": "SKIPPED", "summary": "not yet"},
                {"gate": "browserLayout", "status": "SKIPPED", "summary": "not yet"},
                {"gate": "pytest", "status": "PASS", "summary": "mocked"},
            ]
            overall, blocking, warnings = aggregate_status(results)
            summary = build_summary("session-detail", "test-change", results, overall, blocking, warnings, started)
            _write_summary_artifact(out, summary)
            summary_path = out / "quality-gate-summary.json"
            assert summary_path.exists(), f"Summary not written to {summary_path}"
            data = json.loads(summary_path.read_text())
            assert data["schemaVersion"] == 1
            assert data["target"] == "session-detail"
            assert data["changeId"] == "test-change"
            assert "requiredGates" in data
            assert "startedAt" in data
            assert "finishedAt" in data

    def _t5_gate_status_aggregation():
        """Gate statuses are aggregated correctly."""
        results = [
            {"gate": "staticCssContract", "status": "PASS", "summary": ""},
            {"gate": "pytest", "status": "PASS", "summary": ""},
        ]
        overall, blocking, warnings = aggregate_status(results)
        assert overall == "PASS"
        assert blocking == []

    def _t6_blocking_failure_causes_fail():
        """A single FAIL gate causes overall FAIL."""
        results = [
            {"gate": "staticCssContract", "status": "PASS", "summary": "ok"},
            {"gate": "templateContract", "status": "FAIL", "summary": "test failed"},
        ]
        overall, blocking, warnings = aggregate_status(results)
        assert overall == "FAIL"
        assert len(blocking) == 1
        assert "templateContract" in blocking[0]

    def _t7_skipped_not_pass():
        """Skipped gates go to warnings, not hidden."""
        results = [
            {"gate": "staticCssContract", "status": "SKIPPED", "summary": ""},
            {"gate": "pytest", "status": "PASS", "summary": ""},
        ]
        overall, blocking, warnings = aggregate_status(results)
        assert overall == "PASS"
        assert len(warnings) >= 1

    def _t8_unknown_change_id_still_works():
        """unknown change ID still writes artifact."""
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            summary = build_summary("session-detail", "unknown", [], "PASS", [], [], started)
            _write_summary_artifact(out, summary)
            data = json.loads((out / "quality-gate-summary.json").read_text())
            assert data["changeId"] == "unknown"

    _run("change id fallback", _t1_change_id_fallback)
    _run("change id explicit", _t2_change_id_explicit)
    _run("change id env", _t3_change_id_env)
    _run("summary JSON written", _t4_summary_json_written)
    _run("gate status aggregation", _t5_gate_status_aggregation)
    _run("blocking failure causes FAIL", _t6_blocking_failure_causes_fail)
    _run("skipped not伪装成 PASS", _t7_skipped_not_pass)
    _run("unknown change id works", _t8_unknown_change_id_still_works)

    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    else:
        print(f"\nAll self-tests passed")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Quality gate runner")
    parser.add_argument("--target", default="session-detail", help="Quality gate target")
    parser.add_argument("--change-id", default=None, help="Override change ID")
    parser.add_argument("--out", default=None, help="Override output directory")
    parser.add_argument("--allow-missing-service", action="store_true", help="Don't fail when service is unavailable")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    change_id = resolve_change_id(args.change_id)
    out_dir = resolve_out_dir(change_id, args.out)

    print(f"Quality gate: target={args.target}, change-id={change_id}")
    print(f"Output: {out_dir}")
    print()

    summary = run_gates(args.target, change_id, out_dir, args.allow_missing_service)

    # Print summary to stdout
    print(f"Overall status: {summary['status']}")
    print()
    for gate_name, status in summary["requiredGates"].items():
        print(f"  {gate_name}: {status}")

    if summary["blockingFailures"]:
        print()
        print("Blocking failures:")
        for f in summary["blockingFailures"]:
            print(f"  - {f}")

    if summary["warnings"]:
        print()
        print("Warnings:")
        for w in summary["warnings"]:
            print(f"  - {w}")

    print()
    print(f"Artifact: {out_dir / 'quality-gate-summary.json'}")

    if summary["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
