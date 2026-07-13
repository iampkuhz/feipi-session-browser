from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / 'scripts' / 'hooks' / 'guard_openspec_change.py'


def write_manifest(root: Path) -> None:
    manifest = root / 'harness' / 'agent-runtime.manifest.yaml'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        'protected_roots:\n  - .claude/\n  - .codex/\n  - .qoder/\n  - scripts/\n', encoding='utf-8'
    )


def write_valid_change(root: Path, change_id: str) -> None:
    change_dir = root / 'openspec' / 'changes' / change_id
    spec_dir = change_dir / 'specs' / 'agent-runtime'
    spec_dir.mkdir(parents=True, exist_ok=True)
    for name in ('proposal.md', 'design.md', 'tasks.md'):
        (change_dir / name).write_text(f'# {name}\n', encoding='utf-8')
    (spec_dir / 'spec.md').write_text('# spec\n', encoding='utf-8')


def run_guard(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop('ACTIVE_CHANGE_ID', None)
    merged.pop('FEIPI_SESSION_ID', None)
    merged.pop('FEIPI_AGENT_ID', None)
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(GUARD), '--root', str(root), *args],
        cwd=REPO,
        text=True,
        capture_output=True,
        env=merged,
        check=False,
    )


def test_guard_blocks_protected_path_without_active_change(tmp_path: Path) -> None:
    write_manifest(tmp_path)

    result = run_guard(tmp_path, '--path', '.claude/agents/qwen-main-default.md')

    assert result.returncode == 2
    assert 'BLOCK' in result.stderr


def test_guard_blocks_when_multiple_changes_and_no_selected_id(tmp_path: Path) -> None:
    write_manifest(tmp_path)
    write_valid_change(tmp_path, 'change-a')
    write_valid_change(tmp_path, 'change-b')

    result = run_guard(tmp_path, '--path', '.claude/agents/qwen-main-default.md')

    assert result.returncode == 2
    assert 'Multiple active OpenSpec changes' in result.stderr


def test_guard_blocks_invalid_selected_change(tmp_path: Path) -> None:
    write_manifest(tmp_path)

    result = run_guard(
        tmp_path,
        '--change-id',
        'missing-change',
        '--path',
        '.claude/agents/qwen-main-default.md',
    )

    assert result.returncode == 2
    assert "selected change 'missing-change'" in result.stderr


def test_guard_passes_valid_selected_change(tmp_path: Path) -> None:
    write_manifest(tmp_path)
    write_valid_change(tmp_path, 'valid-change')

    result = run_guard(
        tmp_path,
        '--change-id',
        'valid-change',
        '--path',
        '.claude/agents/qwen-main-default.md',
    )

    assert result.returncode == 0
    assert 'PASS' in result.stdout


def test_guard_does_not_require_change_for_unprotected_path(tmp_path: Path) -> None:
    write_manifest(tmp_path)

    result = run_guard(tmp_path, '--path', 'docs/notes.md')

    assert result.returncode == 0
    assert 'unprotected path' in result.stdout


def copy_runtime_guard_fixture(root: Path) -> None:
    """构造只覆盖共享 Hook 入口→OpenSpec guard 的最小隔离仓库。"""

    write_manifest(root)
    files = [
        'scripts/hooks/guard_openspec_change.py',
        'scripts/openspec/validate_active_change.py',
        'scripts/agent_runtime/policy.py',
    ]
    for rel in files:
        src = REPO / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in (
        'scripts/__init__.py',
        'scripts/agent_runtime/__init__.py',
        'scripts/agent_runtime/session/__init__.py',
        'scripts/harness/__init__.py',
        'scripts/hooks/__init__.py',
        'scripts/openspec/__init__.py',
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    (root / 'scripts' / 'agent_runtime' / 'paths.py').write_text(
        "from pathlib import Path\n"
        "class P:\n"
        "    def __init__(self, root): self.active_change_candidates=[Path(root)/'openspec/active_change.json']\n"
        "def build_paths(repo_root=None): return P(repo_root or Path.cwd())\n"
        "def legacy_active_change_path(root): return Path(root)/'tmp/active_change.json'\n",
        encoding='utf-8',
    )
    (root / 'scripts' / 'agent_runtime' / 'session' / 'contract.py').write_text(
        "def validate_run_write_authorization(*args, **kwargs): return True, [], {}\n"
        "def load_run_record(*args, **kwargs): return None\n",
        encoding='utf-8',
    )
    entry = root / 'scripts' / 'agent_runtime' / 'hook_entry.py'
    entry.write_text(
        "import json, subprocess, sys\n"
        "from pathlib import Path\n"
        "def main():\n"
        "    payload=json.loads(sys.stdin.read() or '{}')\n"
        "    tool_input=payload.get('tool_input') or payload.get('toolInput') or {}\n"
        "    path=tool_input.get('file_path') or tool_input.get('path') or ''\n"
        "    guard=Path.cwd()/'scripts/hooks/guard_openspec_change.py'\n"
        "    proc=subprocess.run([sys.executable,str(guard),'--path',path],text=True,capture_output=True)\n"
        "    if proc.returncode: print((proc.stderr or proc.stdout).strip(),file=sys.stderr)\n"
        "    return 2 if proc.returncode else 0\n"
        "if __name__ == '__main__': raise SystemExit(main())\n",
        encoding='utf-8',
    )


def write_payload(path: str | None = '.claude/agents/qwen-main-default.md') -> str:
    tool_input = {'file_path': path} if path is not None else {}
    return json.dumps(
        {'tool_name': 'Write', 'session_id': 'synthetic-session', 'tool_input': tool_input}
    )


def run_in_fixture(
    root: Path, command: list[str], payload: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop('ACTIVE_CHANGE_ID', None)
    env.pop('FEIPI_SESSION_ID', None)
    env.pop('FEIPI_AGENT_ID', None)
    env['PYTHONPATH'] = str(root)
    return subprocess.run(
        command,
        cwd=root,
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_claude_pre_write_blocks_protected_without_change(tmp_path: Path) -> None:
    copy_runtime_guard_fixture(tmp_path)

    result = run_in_fixture(
        tmp_path,
        [sys.executable, '-m', 'scripts.agent_runtime.hook_entry', 'pre-write'],
        write_payload(),
    )

    assert result.returncode == 2
    assert 'OpenSpec guard BLOCK' in result.stderr


def test_codex_pre_write_blocks_protected_without_change(tmp_path: Path) -> None:
    copy_runtime_guard_fixture(tmp_path)

    result = run_in_fixture(
        tmp_path,
        [sys.executable, '-m', 'scripts.agent_runtime.hook_entry', 'pre-write'],
        write_payload(),
    )

    assert result.returncode == 2
    assert 'OpenSpec guard BLOCK' in result.stderr


def test_qoder_pre_write_blocks_protected_without_change(tmp_path: Path) -> None:
    copy_runtime_guard_fixture(tmp_path)

    result = run_in_fixture(
        tmp_path,
        [sys.executable, '-m', 'scripts.agent_runtime.hook_entry', 'pre-write'],
        write_payload(),
    )

    assert result.returncode == 2
    assert 'OpenSpec guard BLOCK' in result.stderr
