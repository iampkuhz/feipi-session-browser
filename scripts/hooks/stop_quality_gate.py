#!/usr/bin/env python3
"""Stop hook quality gate enforcement.

Reads tmp/agent_logs/current/changed-files.jsonl and
tmp/quality/<change-id>/quality-gate-summary.json to determine if UI changes have passed required quality gates.

This is a DETERMINISTIC check — it does NOT run browsers, LLMs, or subagents.

Usage:
    python3 scripts/hooks/stop_quality_gate.py
    python3 scripts/hooks/stop_quality_gate.py --change-id fix-xyz
    python3 scripts/hooks/stop_quality_gate.py --self-test

Exit codes:
    0  PASS — no UI changes or quality artifact confirms PASS
    1  FAIL — UI changes without PASS artifact, or artifact is FAIL/stale
"""

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANGED_FILES = REPO_ROOT / 'tmp' / 'agent_logs' / 'current' / 'changed-files.jsonl'
QUALITY_DIR = REPO_ROOT / 'tmp' / 'quality'

UI_CATEGORIES = {'ui-css', 'ui-template', 'ui-js'}
HOOK_QUALITY_CATEGORIES = {'hook', 'quality-gate'}


def resolve_change_id(explicit: str | None) -> str:
    """Resolve the change id used by the stop hook quality artifact lookup.

    Args:
        explicit: Optional CLI override.

    Returns:
        Explicit id, tmp/active_change.json id, or 'unknown' when neither is available.
    """
    if explicit:
        return explicit
    # Read from tmp/active_change.json (written by agent during OpenSpec change)
    active_change = REPO_ROOT / 'tmp' / 'active_change.json'
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            cid = data.get('change_id', '')
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            pass
    return 'unknown'


def read_changed_files() -> list[dict]:
    """Read changed-file records captured by agent hooks for stop-hook enforcement.

    Returns:
        List of parsed JSON records; malformed lines and missing files are ignored.
    """
    if not CHANGED_FILES.exists():
        return []
    entries = []
    for raw_line in CHANGED_FILES.read_text(encoding='utf-8').strip().split('\n'):
        line = raw_line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def has_ui_changes(entries: list[dict]) -> tuple[bool, list[str]]:
    """Identify UI changes that require a session-detail quality artifact.

    Args:
        entries: Changed-file records from read_changed_files.

    Returns:
        Tuple indicating whether UI files changed and the matching file paths.
    """
    ui_files = [e['file'] for e in entries if e.get('category') in UI_CATEGORIES]
    return bool(ui_files), ui_files


def has_hook_quality_changes(entries: list[dict]) -> tuple[bool, list[str]]:
    """Identify hook or quality-gate edits tracked by the stop hook.

    Args:
        entries: Changed-file records from read_changed_files.

    Returns:
        Tuple indicating whether hook/quality files changed and the matching file paths.
    """
    files = [e['file'] for e in entries if e.get('category') in HOOK_QUALITY_CATEGORIES]
    return bool(files), files


def get_latest_ui_edit_time(entries: list[dict]) -> str | None:
    """Find the newest UI edit timestamp for stale artifact detection.

    Args:
        entries: Changed-file records from read_changed_files.

    Returns:
        Latest UI timestamp string, or None when no UI timestamp exists.
    """
    ui_times = [e['ts'] for e in entries if e.get('category') in UI_CATEGORIES and e.get('ts')]
    return max(ui_times) if ui_times else None


def read_quality_artifact(change_id: str) -> dict | None:
    """Read the session-detail quality artifact for the active change.

    Args:
        change_id: Change id used to locate tmp/quality/<change-id>.

    Returns:
        Parsed artifact dictionary, or None when the artifact is missing or invalid.
    """
    target_specific = QUALITY_DIR / change_id / 'quality-gate-summary.session-detail.json'
    if not target_specific.exists():
        return None
    try:
        return json.loads(target_specific.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def is_artifact_stale(artifact: dict, latest_ui_edit: str | None) -> bool:
    """Compare quality artifact completion time with the newest UI edit time.

    Args:
        artifact: Parsed quality artifact dictionary.
        latest_ui_edit: Newest UI edit timestamp from changed-file records.

    Returns:
        True when the artifact is missing a finish time or predates the UI edit; otherwise False.
    """
    if not latest_ui_edit or not artifact:
        return False
    finished_at = artifact.get('finishedAt', '')
    if not finished_at:
        return True
    # Simple string comparison works for ISO 8601 UTC timestamps
    return finished_at < latest_ui_edit


def run_check(change_id: str | None = None) -> tuple[str, list[str]]:  # noqa: PLR0911 - hook exits by scenario.
    """Evaluate whether the stop hook may allow the agent turn to finish.

    Args:
        change_id: Optional explicit change id; None resolves from active-change state.

    Returns:
        Tuple of PASS/FAIL status and human-readable blocking messages.
    """
    cid = resolve_change_id(change_id)
    # Read changed files
    entries = read_changed_files()
    if not entries:
        return 'PASS', []

    # Check for UI changes
    has_ui, ui_files = has_ui_changes(entries)
    if not has_ui:
        # No UI changes — check if hook/quality files changed
        has_hq, _hq_files = has_hook_quality_changes(entries)
        if not has_hq:
            return 'PASS', []
        # Hook/quality files changed — require artifact PASS
        artifact = read_quality_artifact(cid)
        if artifact is None:
            return 'PASS', []  # No UI changes, hook changes don't require UI gate
        if artifact.get('status') != 'PASS':
            return 'FAIL', [
                f"Quality gate artifact status is '{artifact.get('status')}' (expected PASS).",
                'Run: python3 scripts/quality/run_quality_gate.py --target session-detail',
            ]
        return 'PASS', []

    # UI changes exist — require quality artifact
    artifact = read_quality_artifact(cid)

    if artifact is None:
        return 'FAIL', [
            'BLOCK: UI files changed but required quality artifact is missing or stale.',
            '',
            'Changed UI files:',
        ] + [f'  - {f}' for f in ui_files] + [
            '',
            'Required:',
            '  python3 scripts/quality/run_quality_gate.py --target session-detail',
            '',
            'Expected artifact:',
            f'  tmp/quality/{cid}/quality-gate-summary.session-detail.json',
            '',
            'Reason:',
            '  missing artifact',
        ]

    # Artifact exists but is FAIL
    if artifact.get('status') != 'PASS':
        blocking = artifact.get('blockingFailures', [])
        summary = f'Artifact status: {artifact.get("status")}'
        if blocking:
            summary += '\n  Blocking failures:\n' + '\n'.join(f'    - {b}' for b in blocking[:5])
        return 'FAIL', [
            'BLOCK: UI files changed but quality gate did not PASS.',
            '',
            'Changed UI files:',
        ] + [f'  - {f}' for f in ui_files] + [
            '',
            'Artifact summary:',
            f'  {summary}',
        ]

    # Artifact is PASS — check staleness
    latest_ui_edit = get_latest_ui_edit_time(entries)
    if is_artifact_stale(artifact, latest_ui_edit):
        return 'FAIL', [
            'BLOCK: Quality artifact is stale (older than latest UI edit).',
            '',
            f'Latest UI edit: {latest_ui_edit}',
            f'Artifact finished: {artifact.get("finishedAt", "unknown")}',
            '',
            'Re-run: python3 scripts/quality/run_quality_gate.py --target session-detail',
        ]

    return 'PASS', [f'Quality gate PASS (change-id={cid})']


def _self_test() -> None:  # noqa: PLR0915 - embedded scenarios stay local to hook.
    """Run deterministic stop-hook scenarios without touching real quality artifacts."""
    failures = 0

    def _run(name: str, func: Callable[[], None]) -> None:
        """Execute one embedded stop-hook self-test and count failures.

        Args:
            name: Scenario label printed in self-test output.
            func: Callable containing assertions for the scenario.
        """
        nonlocal failures
        try:
            func()
            print(f'  PASS: {name}')
        except AssertionError as e:
            failures += 1
            print(f'  FAIL: {name} — {e}')
        except Exception as e:
            failures += 1
            print(f'  FAIL: {name} — {type(e).__name__}: {e}')

    def _make_artifact(status: str, finished: str = '2026-05-18T00:01:00Z') -> dict:
        """Build a minimal quality artifact for stop-hook self-tests.

        Args:
            status: Artifact status to encode.
            finished: Finished timestamp used for stale checks.

        Returns:
            Dictionary shaped like a session-detail quality-gate summary.
        """
        return {
            'schemaVersion': 1,
            'status': status,
            'target': 'session-detail',
            'changeId': 'test',
            'startedAt': '2026-05-18T00:00:00Z',
            'finishedAt': finished,
            'requiredGates': {},
            'blockingFailures': [],
            'warnings': [],
            'artifacts': {},
        }

    def _t1_no_changed_files() -> None:
        """No changed-files => PASS."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                status, msgs = run_check('test')
                assert status == 'PASS', f'Expected PASS, got {status}'
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t2_ui_missing_artifact() -> None:
        """UI file changed, artifact missing => FAIL."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                CHANGED_FILES.write_text(
                    json.dumps(
                        {
                            'ts': '2026-05-18T00:00:00Z',
                            'tool': 'Edit',
                            'file': 'src/session_browser/web/static/style.css',
                            'category': 'ui-css',
                            'requiresQualityGate': True,
                        }
                    )
                    + '\n'
                )
                status, msgs = run_check('test')
                assert status == 'FAIL', f'Expected FAIL, got {status}'
                assert 'missing' in ' '.join(msgs).lower(), "Expected 'missing' in messages"
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t3_ui_artifact_fail() -> None:
        """UI file changed, artifact FAIL => FAIL."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                QUALITY_DIR.mkdir(parents=True)
                CHANGED_FILES.write_text(
                    json.dumps(
                        {
                            'ts': '2026-05-18T00:00:00Z',
                            'tool': 'Edit',
                            'file': 'src/session_browser/web/static/style.css',
                            'category': 'ui-css',
                            'requiresQualityGate': True,
                        }
                    )
                    + '\n'
                )
                art = _make_artifact('FAIL')
                art['blockingFailures'] = ['css: missing rule']
                (QUALITY_DIR / 'test' / 'quality-gate-summary.session-detail.json').parent.mkdir(
                    parents=True, exist_ok=True
                )
                (QUALITY_DIR / 'test' / 'quality-gate-summary.session-detail.json').write_text(
                    json.dumps(art)
                )
                status, _msgs = run_check('test')
                assert status == 'FAIL', f'Expected FAIL, got {status}'
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t4_ui_artifact_stale() -> None:
        """UI file changed, artifact PASS but stale => FAIL."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                QUALITY_DIR.mkdir(parents=True)
                CHANGED_FILES.write_text(
                    json.dumps(
                        {
                            'ts': '2026-05-18T00:02:00Z',
                            'tool': 'Edit',
                            'file': 'src/session_browser/web/static/style.css',
                            'category': 'ui-css',
                            'requiresQualityGate': True,
                        }
                    )
                    + '\n'
                )
                art = _make_artifact('PASS', finished='2026-05-18T00:01:00Z')
                (QUALITY_DIR / 'test' / 'quality-gate-summary.session-detail.json').parent.mkdir(
                    parents=True, exist_ok=True
                )
                (QUALITY_DIR / 'test' / 'quality-gate-summary.session-detail.json').write_text(
                    json.dumps(art)
                )
                status, _msgs = run_check('test')
                assert status == 'FAIL', f'Expected FAIL (stale), got {status}'
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t5_ui_artifact_pass_fresh() -> None:
        """UI file changed, artifact PASS and fresh => PASS."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                QUALITY_DIR.mkdir(parents=True)
                CHANGED_FILES.write_text(
                    json.dumps(
                        {
                            'ts': '2026-05-18T00:00:00Z',
                            'tool': 'Edit',
                            'file': 'src/session_browser/web/static/style.css',
                            'category': 'ui-css',
                            'requiresQualityGate': True,
                        }
                    )
                    + '\n'
                )
                art = _make_artifact('PASS', finished='2026-05-18T00:01:00Z')
                (QUALITY_DIR / 'test' / 'quality-gate-summary.session-detail.json').parent.mkdir(
                    parents=True, exist_ok=True
                )
                (QUALITY_DIR / 'test' / 'quality-gate-summary.session-detail.json').write_text(
                    json.dumps(art)
                )
                status, _msgs = run_check('test')
                assert status == 'PASS', f'Expected PASS, got {status}'
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t6_docs_only() -> None:
        """Only docs changed => PASS."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                CHANGED_FILES.write_text(
                    json.dumps(
                        {
                            'ts': '2026-05-18T00:00:00Z',
                            'tool': 'Edit',
                            'file': 'README.md',
                            'category': 'other',
                            'requiresQualityGate': False,
                        }
                    )
                    + '\n'
                )
                status, _msgs = run_check('test')
                assert status == 'PASS', f'Expected PASS, got {status}'
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    def _t7_unknown_change_id() -> None:
        """Unknown change ID still checks tmp/quality/unknown."""
        with tempfile.TemporaryDirectory() as td:
            global CHANGED_FILES, QUALITY_DIR  # noqa: PLW0603 - self-test swaps temp paths.
            old_cf, old_qd = CHANGED_FILES, QUALITY_DIR
            try:
                CHANGED_FILES = Path(td) / 'changed-files.jsonl'
                QUALITY_DIR = Path(td) / 'quality'
                CHANGED_FILES.write_text(
                    json.dumps(
                        {
                            'ts': '2026-05-18T00:00:00Z',
                            'tool': 'Edit',
                            'file': 'src/session_browser/web/static/style.css',
                            'category': 'ui-css',
                            'requiresQualityGate': True,
                        }
                    )
                    + '\n'
                )
                status, _msgs = run_check('unknown')
                # No artifact for "unknown" => FAIL
                assert status == 'FAIL', f'Expected FAIL, got {status}'
            finally:
                CHANGED_FILES, QUALITY_DIR = old_cf, old_qd

    _run('no changed-files => PASS', _t1_no_changed_files)
    _run('UI changed, artifact missing => FAIL', _t2_ui_missing_artifact)
    _run('UI changed, artifact FAIL => FAIL', _t3_ui_artifact_fail)
    _run('UI changed, artifact stale => FAIL', _t4_ui_artifact_stale)
    _run('UI changed, artifact PASS fresh => PASS', _t5_ui_artifact_pass_fresh)
    _run('docs only changed => PASS', _t6_docs_only)
    _run('unknown change ID checks quality/unknown', _t7_unknown_change_id)

    if failures:
        print(f'\n{failures} test(s) failed')
        sys.exit(1)
    else:
        print('\nAll self-tests passed')
        sys.exit(0)


def main() -> None:
    """Parse stop-hook CLI options and enforce the session-detail quality gate."""
    parser = argparse.ArgumentParser(description='Stop hook quality gate')
    parser.add_argument('--change-id', default=None, help='Override change ID')
    parser.add_argument('--self-test', action='store_true', help='Run self-tests')
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return

    status, messages = run_check(args.change_id)

    # 输出简洁摘要
    if status == 'PASS':
        print('[stop_quality_gate] PASS', file=sys.stdout)
        for msg in messages:
            print(msg, file=sys.stdout)
    else:
        print('[stop_quality_gate] BLOCK', file=sys.stderr)
        print(file=sys.stderr)
        for msg in messages:
            print(msg, file=sys.stderr)
        print(file=sys.stderr)
        print('--- 精确 rerun 命令 ---', file=sys.stderr)
        print(
            '  python3 scripts/quality/run_quality_gate.py --target session-detail '
            f'--change-id {resolve_change_id(args.change_id)}',
            file=sys.stderr,
        )

    if status == 'FAIL':
        sys.exit(1)


if __name__ == '__main__':
    main()
