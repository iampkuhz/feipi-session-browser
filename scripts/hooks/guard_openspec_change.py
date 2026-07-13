#!/usr/bin/env python3
"""本模块负责执行 `guard_openspec_change` 对应的确定性仓库检查。

不负责执行被保护写入；由平台 Hook runtime 调用。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_runtime.paths import build_paths, legacy_active_change_path  # noqa: E402
from scripts.agent_runtime.policy import is_protected_path  # noqa: E402
from scripts.agent_runtime.session.contract import validate_run_write_authorization  # noqa: E402
from scripts.openspec.validate_active_change import validate_change_at_root  # noqa: E402


@dataclass(frozen=True)
class Resolution:
    """保存 active change 解析结果与选择来源，供 Hook guard 判定。"""

    change_id: str | None
    source: str
    explicit: bool = False
    errors: tuple[str, ...] = ()


def _repo_root(root: str | Path | None = None) -> Path:
    return Path(root).resolve() if root else REPO_ROOT


def _read_change_id_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        data: Any = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if isinstance(data, dict):
        value = data.get('change_id') or data.get('changeId') or data.get('id')
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _runtime_active_change(root: Path) -> tuple[str | None, str]:
    try:
        paths = build_paths(repo_root=root)
    except Exception:
        return None, 'runtime'
    legacy = legacy_active_change_path(root).resolve()
    for candidate in paths.active_change_candidates:
        try:
            if candidate.resolve() == legacy:
                continue
        except Exception:
            pass
        change_id = _read_change_id_file(candidate)
        if change_id:
            return change_id, str(candidate)
    return None, 'runtime'


def _non_archive_changes(root: Path) -> list[str]:
    changes_dir = root / 'openspec' / 'changes'
    if not changes_dir.is_dir():
        return []
    return sorted(p.name for p in changes_dir.iterdir() if p.is_dir() and p.name != 'archive')


def resolve_active_change(
    *,
    root: str | Path | None = None,
    cli_change_id: str | None = None,
    env: dict[str, str] | None = None,
) -> Resolution:
    """参数：
        root: 仓库根目录覆盖值。
        cli_change_id: 命令行显式 change id。
        env: 环境变量映射。

    返回：
        active change 解析结果。
    """
    base = _repo_root(root)
    environ = env if env is not None else os.environ
    if cli_change_id and cli_change_id.strip():
        return Resolution(cli_change_id.strip(), '--change-id', explicit=True)

    env_run = environ.get('FEIPI_RUN_ID', '').strip()
    if env_run:
        from scripts.agent_runtime.session.contract import load_run_record

        record = load_run_record(base, env_run)
        if record and record.get('changeId'):
            return Resolution(str(record['changeId']), f'run record {env_run}', explicit=True)

    env_change = environ.get('ACTIVE_CHANGE_ID', '').strip()
    if env_change:
        return Resolution(env_change, 'ACTIVE_CHANGE_ID', explicit=True)

    runtime_change, runtime_source = _runtime_active_change(base)
    if runtime_change:
        return Resolution(runtime_change, runtime_source)

    legacy_change = _read_change_id_file(base / 'tmp' / 'active_change.json')
    if legacy_change:
        return Resolution(
            legacy_change,
            'tmp/active_change.json',
            errors=('legacy active change fallback; not valid for bound writable runs',),
        )

    changes = _non_archive_changes(base)
    if len(changes) == 1:
        return Resolution(changes[0], 'single non-archive change')
    if len(changes) > 1:
        return Resolution(
            None,
            'auto-discovery',
            errors=(
                'Multiple active OpenSpec changes found and no explicit active change was selected.',
            ),
        )
    return Resolution(None, 'auto-discovery', errors=('No active OpenSpec change selected.',))


def guard_path(
    path: str | None = None,
    *,
    root: str | Path | None = None,
    change_id: str | None = None,
    env: dict[str, str] | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    client: str | None = None,
) -> tuple[int, str]:
    """参数：
        path: 候选写入路径。
        root: 仓库根目录覆盖值。
        change_id: 显式 change id。
        env: 环境变量映射。

    返回：
        guard 退出码和用户可读消息。
    """
    base = _repo_root(root)
    if path and not is_protected_path(path, base):
        return 0, f'OpenSpec guard PASS: unprotected path does not require change: {path}'

    environ = env if env is not None else os.environ
    selected_run = (run_id or environ.get('FEIPI_RUN_ID', '')).strip()
    selected_session = (session_id or environ.get('FEIPI_SESSION_ID', '')).strip()
    selected_client = (
        client or environ.get('FEIPI_AGENT_CLIENT', '') or environ.get('FEIPI_CLIENT', '')
    ).strip()
    resolution = resolve_active_change(root=base, cli_change_id=change_id, env=env)
    if selected_run:
        from scripts.agent_runtime.session.contract import load_run_record

        run_record = load_run_record(base, selected_run) or {}
        authoritative_change = str(run_record.get('changeId') or resolution.change_id or '')
        ok, auth_errors, record = validate_run_write_authorization(
            base,
            client=selected_client or str(run_record.get('client') or ''),
            session_id=selected_session,
            run_id=selected_run,
            change_id=authoritative_change,
            candidate_paths=[path] if path else [],
        )
        if change_id and resolution.change_id and authoritative_change != resolution.change_id:
            ok = False
            auth_errors.append('current change id does not match run record')
        if not ok:
            return 2, 'OpenSpec guard BLOCK: run-scoped authorization failed: ' + '; '.join(
                auth_errors
            )
    if not resolution.change_id:
        detail = (
            '; '.join(resolution.errors)
            if resolution.errors
            else 'No active OpenSpec change selected.'
        )
        return 2, f'OpenSpec guard BLOCK: {detail}'

    errors = validate_change_at_root(resolution.change_id, base)
    if errors:
        lines = '\n'.join(f'  - {item}' for item in errors)
        return (
            2,
            f"OpenSpec guard BLOCK: selected change '{resolution.change_id}' from {resolution.source} is invalid:\n{lines}",
        )
    target = path or '<protected write>'
    return (
        0,
        f"OpenSpec guard PASS: protected path {target} is covered by active change '{resolution.change_id}' ({resolution.source})",
    )


def _write_valid_change(root: Path, change_id: str) -> None:
    change_dir = root / 'openspec' / 'changes' / change_id
    specs_dir = change_dir / 'specs' / 'agent-runtime'
    specs_dir.mkdir(parents=True, exist_ok=True)
    for name in ('proposal.md', 'design.md', 'tasks.md'):
        (change_dir / name).write_text(f'# {name}\n', encoding='utf-8')
    (specs_dir / 'spec.md').write_text('# spec\n', encoding='utf-8')


def _write_manifest(root: Path) -> None:
    manifest = root / 'harness' / 'agent-runtime.manifest.yaml'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('protected_roots:\n  - .claude/\n  - scripts/\n', encoding='utf-8')


def run_self_test() -> bool:
    """执行 `run_self_test` 对应的仓库检查流程；失败时保留可诊断的退出语义。"""
    tmp_root = Path(tempfile.mkdtemp(prefix='openspec_guard_selftest_'))
    try:
        _write_manifest(tmp_root)
        code, _ = guard_path('docs/readme.md', root=tmp_root, env={})
        if code != 0:
            print('  FAIL: unprotected path should pass')
            return False
        code, _ = guard_path('.claude/agents/a.md', root=tmp_root, env={})
        if code != 2:
            print('  FAIL: protected path without active change should block')
            return False
        _write_valid_change(tmp_root, 'valid-change')
        code, _ = guard_path('.claude/agents/a.md', root=tmp_root, change_id='valid-change', env={})
        if code != 0:
            print('  FAIL: valid selected change should pass')
            return False
        code, _ = guard_path(
            '.claude/agents/a.md', root=tmp_root, change_id='missing-change', env={}
        )
        if code != 2:
            print('  FAIL: invalid selected change should block')
            return False
        _write_valid_change(tmp_root, 'another-change')
        code, _ = guard_path('.claude/agents/a.md', root=tmp_root, env={})
        if code != 2:
            print('  FAIL: multiple changes without selected id should block')
            return False
        print('self-test: PASS')
        return True
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    parser = argparse.ArgumentParser(description='Fail-closed OpenSpec active change guard')
    parser.add_argument('--change-id', help='explicit active change id')
    parser.add_argument('--path', help='candidate path to guard')
    parser.add_argument('--run-id', help='bound primary run id')
    parser.add_argument('--session-id', help='bound primary session id')
    parser.add_argument('--client', help='agent client for run authorization')
    parser.add_argument('--self-test', action='store_true', help='run embedded self-test')
    parser.add_argument('--root', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if run_self_test() else 1

    code, message = guard_path(
        args.path,
        root=args.root,
        change_id=args.change_id,
        run_id=args.run_id,
        session_id=args.session_id,
        client=args.client,
    )
    stream = sys.stdout if code == 0 else sys.stderr
    print(message, file=stream)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
