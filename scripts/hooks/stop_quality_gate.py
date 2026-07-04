#!/usr/bin/env python3
"""提供 stop quality gate 脚本能力。"""

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.claude_hooks import paths as runtime_paths  # noqa: E402

IDENTITY = runtime_paths.identity_from_values()
CHANGED_FILES = runtime_paths.agent_log_dir(REPO_ROOT, IDENTITY) / 'changed-files.jsonl'
QUALITY_DIR = (
    runtime_paths.quality_dir(REPO_ROOT, IDENTITY)
    if IDENTITY.has_session
    else REPO_ROOT / 'tmp' / 'quality'
)

UI_CATEGORIES = {'ui-css', 'ui-template', 'ui-js'}
HOOK_QUALITY_CATEGORIES = {'hook', 'quality-gate'}


# 解析change id。
def resolve_change_id(explicit: str | None) -> str:
    """参数：
        explicit: 可选CLI override。

    返回：
        resolve change id 字符串。
    """
    if explicit:
        return explicit
    if IDENTITY.has_session:
        candidates = runtime_paths.build_paths(REPO_ROOT, IDENTITY).active_change_candidates
    else:
        candidates = [runtime_paths.legacy_active_change_path(REPO_ROOT)]
    for active_change in candidates:
        if not active_change.exists():
            continue
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            cid = data.get('change_id') or data.get('changeId') or ''
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            continue
    return 'unknown'


# 读取changed-files 文件。
def read_changed_files() -> list[dict]:
    """返回：
        解析出的 JSON record 列表；忽略 malformed 行和缺失文件。
    """
    if IDENTITY.has_session:
        log_dirs = runtime_paths.session_log_dirs(
            REPO_ROOT,
            IDENTITY,
            include_agents=not IDENTITY.is_agent,
        )
        changed_paths = [path / 'changed-files.jsonl' for path in log_dirs]
    else:
        changed_paths = [CHANGED_FILES]
    entries = []
    for changed_file in changed_paths:
        if not changed_file.exists():
            continue
        for raw_line in changed_file.read_text(encoding='utf-8').strip().split('\n'):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if IDENTITY.raw_session_id and record.get('sessionId') != IDENTITY.raw_session_id:
                continue
            if IDENTITY.raw_agent_id and record.get('agentId') != IDENTITY.raw_agent_id:
                continue
            entries.append(record)
    return entries


# 判断是否存在UI changes。
def has_ui_changes(entries: list[dict]) -> tuple[bool, list[str]]:
    """参数：
        entries: changed-文件 record从 读取_changed_files。

    返回：
        Tuple indicating whether UI 文件 changed 和 matching 文件路径s。
    """
    ui_files = [e['file'] for e in entries if e.get('category') in UI_CATEGORIES]
    return bool(ui_files), ui_files


# 判断是否存在hook quality changes。
def has_hook_quality_changes(entries: list[dict]) -> tuple[bool, list[str]]:
    """参数：
        entries: changed-文件 record从 读取_changed_files。

    返回：
        Tuple indicating whether hook/quality 文件 changed 和 matching 文件路径s。
    """
    files = [e['file'] for e in entries if e.get('category') in HOOK_QUALITY_CATEGORIES]
    return bool(files), files


# 读取latest UI edit time。
def get_latest_ui_edit_time(entries: list[dict]) -> str | None:
    """参数：
        entries: changed-文件 record从 读取_changed_files。

    返回：
        Latest UI timestamp 字符串, 或 None 当 no UI timestamp exists。
    """
    ui_times = [e['ts'] for e in entries if e.get('category') in UI_CATEGORIES and e.get('ts')]
    return max(ui_times) if ui_times else None


# 读取quality artifact。
def read_quality_artifact(change_id: str) -> dict | None:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        已解析的artifact dictionary, 或 None 当 artifact is 缺失 或 无效。
    """
    target_specific = QUALITY_DIR / change_id / 'quality-gate-summary.session-detail.json'
    if not target_specific.exists():
        return None
    try:
        return json.loads(target_specific.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


# 判断是否artifact stale。
def is_artifact_stale(artifact: dict, latest_ui_edit: str | None) -> bool:
    """参数：
        artifact: 已解析的quality artifact dictionary。
        latest_ui_edit: 最新 UI 编辑 timestamp。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    if not latest_ui_edit or not artifact:
        return False
    finished_at = artifact.get('finishedAt', '')
    if not finished_at:
        return True
    # Simple 字符串 比较 works用于ISO 8601 UTC timestamps。
    return finished_at < latest_ui_edit


# 运行检查。
def run_check(change_id: str | None = None) -> tuple[str, list[str]]:  # noqa: PLR0911 - hook exits by scenario.
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        由PASS/FAIL 状态 和 human-读取able 阻断 messages.组成的 tuple。
    """
    cid = resolve_change_id(change_id)
    # 读取changed 文件。
    entries = read_changed_files()
    if not entries:
        return 'PASS', []

    # 检查用于 UI changes。
    has_ui, ui_files = has_ui_changes(entries)
    if not has_ui:
        # 没有UI changes — check 如果 hook/quality 文件 changed。
        has_hq, _hq_files = has_hook_quality_changes(entries)
        if not has_hq:
            return 'PASS', []
        artifact = read_quality_artifact(cid)
        if artifact is None:
            return 'PASS', []  # No UI changes, hook changes don't require UI gate
        if artifact.get('status') != 'PASS':
            return 'FAIL', [
                f"Quality gate artifact status is '{artifact.get('status')}' (expected PASS).",
                'Run: python3 scripts/quality/run_quality_gate.py --target session-detail',
            ]
        return 'PASS', []

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


# 运行脚本自测试场景。
def _self_test() -> None:  # noqa: PLR0915 - embedded scenarios stay local to hook.
    failures = 0

    # 运行检查流程。
    def _run(name: str, func: Callable[[], None]) -> None:
        """参数：
            name: 条目名称。
            func: func 参数。
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

    # 维护make artifact。
    def _make_artifact(status: str, finished: str = '2026-05-18T00:01:00Z') -> dict:
        """参数：
            status: Artifact 状态到encode。
            finished: finished 参数。

        返回：
            结果映射。
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

    # 维护t1 无 changed-files 文件。
    def _t1_no_changed_files() -> None:
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

    # 维护t2 UI missing artifact。
    def _t2_ui_missing_artifact() -> None:
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

    # 维护t3 UI artifact fail。
    def _t3_ui_artifact_fail() -> None:
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

    # 维护t4 UI artifact stale。
    def _t4_ui_artifact_stale() -> None:
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

    # 维护t5 UI artifact 通过 fresh。
    def _t5_ui_artifact_pass_fresh() -> None:
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

    # 维护t6 docs 仅。
    def _t6_docs_only() -> None:
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

    # 维护t7 unknown change id。
    def _t7_unknown_change_id() -> None:
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
                # 没有artifact用于"unknown" => FAIL。
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


# 解析命令行参数并运行脚本入口。
def main() -> None:
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
