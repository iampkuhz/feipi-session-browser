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
    manifest.write_text('protected_roots:\n  - .claude/\n  - .codex/\n  - .qoder/\n  - scripts/\n', encoding='utf-8')


def write_valid_change(root: Path, change_id: str) -> None:
    change_dir = root / 'openspec' / 'changes' / change_id
    spec_dir = change_dir / 'specs' / 'agent-runtime'
    spec_dir.mkdir(parents=True, exist_ok=True)
    for name in ('proposal.md', 'design.md', 'tasks.md'):
        (change_dir / name).write_text(f'# {name}\n', encoding='utf-8')
    (spec_dir / 'spec.md').write_text('# spec\n', encoding='utf-8')


def run_guard(root: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
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
    write_manifest(root)
    files = [
        'scripts/hooks/guard_openspec_change.py',
        'scripts/openspec/validate_active_change.py',
        'scripts/agent_runtime/policy.py',
        'scripts/claude_hooks/paths.py',
        'scripts/claude_hooks/main.py',
        'scripts/claude_hooks/policy/file_policy.py',
        '.codex/hooks/pre_write_guard.sh',
        '.qoder/hooks/pre_write_guard.sh',
        'scripts/harness/hook-common.sh',
    ]
    for rel in files:
        src = REPO / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in [
        'scripts/agent_runtime/__init__.py',
        'scripts/harness/__init__.py',
        'scripts/claude_hooks/__init__.py',
        'scripts/claude_hooks/policy/__init__.py',
        'scripts/quality/__init__.py',
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    (root / 'scripts' / 'claude_hooks' / 'classify.py').write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class C:\n"
        "    category: str = 'unknown'\n"
        "    requires_quality_gate: bool = False\n"
        "    quality_target: str | None = None\n"
        "def classify_file(path: str) -> C:\n"
        "    return C(category='protected' if path.startswith(('.claude/', '.codex/', '.qoder/', 'scripts/')) else 'unknown')\n",
        encoding='utf-8',
    )
    (root / 'scripts' / 'claude_hooks' / 'evidence.py').write_text(
        "def record_hook_event(*args, **kwargs): return None\n"
        "def acquire_bash_mutation_lock(*args, **kwargs): return True\n"
        "def read_bash_mutation_lock_info(*args, **kwargs): return {}\n"
        "def record_post_bash(*args, **kwargs): return []\n"
        "def record_post_write(*args, **kwargs): return []\n"
        "def record_pre_bash_snapshot(*args, **kwargs): return True\n",
        encoding='utf-8',
    )
    harness = root / 'scripts' / 'harness' / 'primary_session.py'
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text(
        "def validate_run_write_authorization(*args, **kwargs): return (True, [], {})\n"
        "def validate_legacy_single_writer(*args, **kwargs): return []\n"
        "def load_run_record(*args, **kwargs): return None\n",
        encoding='utf-8',
    )
    worktree = root / 'scripts' / 'agent_runtime' / 'worktree.py'
    worktree.parent.mkdir(parents=True, exist_ok=True)
    worktree.write_text(
        "class D:\n"
        "    allowed=True; required=False; assigned=True; reason=''\n"
        "    def as_dict(self): return {'allowed': True}\n"
        "def check_session_worktree(*args, **kwargs): return D()\n",
        encoding='utf-8',
    )
    (root / 'scripts' / 'claude_hooks' / 'hook_io.py').write_text(
        "import json, sys\n"
        "class HookContext:\n"
        "    def __init__(self, event_name, raw=None, parse_error=None): self.event_name=event_name; self.raw=raw or {}; self.parse_error=parse_error\n"
        "    @property\n"
        "    def tool_name(self): return str(self.raw.get('tool_name') or self.raw.get('toolName') or '')\n"
        "    @property\n"
        "    def tool_input(self):\n"
        "        value=self.raw.get('tool_input') or self.raw.get('toolInput') or {}\n"
        "        return value if isinstance(value, dict) else {}\n"
        "    @property\n"
        "    def command(self): return str(self.tool_input.get('command') or '')\n"
        "    @property\n"
        "    def session_id(self): return str(self.raw.get('session_id') or self.raw.get('sessionId') or '')\n"
        "    @property\n"
        "    def agent_id(self): return str(self.raw.get('agent_id') or self.raw.get('agentId') or '')\n"
        "    @property\n"
        "    def agent_client(self): return str(self.raw.get('agent_client') or self.raw.get('agentClient') or self.raw.get('client') or '')\n"
        "    @property\n"
        "    def run_id(self): return str(self.raw.get('run_id') or self.raw.get('runId') or '')\n"
        "    @property\n"
        "    def task_id(self): return str(self.raw.get('task_id') or self.raw.get('taskId') or '')\n"
        "    @property\n"
        "    def worktree_id(self): return str(self.raw.get('worktree_id') or self.raw.get('worktreeId') or '')\n"
        "    @property\n"
        "    def turn_id(self): return str(self.raw.get('turn_id') or self.raw.get('turnId') or '')\n"
        "    @property\n"
        "    def stop_hook_active(self): return False\n"
        "    @property\n"
        "    def cwd(self): return str(self.raw.get('cwd') or '')\n"
        "    @property\n"
        "    def candidate_paths(self):\n"
        "        out=[]\n"
        "        for k in ('file_path','path','notebook_path'):\n"
        "            v=self.tool_input.get(k)\n"
        "            if isinstance(v,str) and v: out.append(v)\n"
        "        return list(dict.fromkeys(out))\n"
        "def read_stdin_json(event_name, stdin_text=None):\n"
        "    text = sys.stdin.read() if stdin_text is None else stdin_text\n"
        "    return HookContext(event_name, json.loads(text) if text.strip() else {})\n",
        encoding='utf-8',
    )
    (root / 'scripts' / 'claude_hooks' / 'result.py').write_text(
        "import json, sys\n"
        "from dataclasses import dataclass, field\n"
        "@dataclass\n"
        "class HookResult:\n"
        "    status: str='PASS'; exit_code: int=0; message: str=''; warnings: list=field(default_factory=list); details: dict=field(default_factory=dict)\n"
        "def emit(result):\n"
        "    if result.status != 'PASS' or result.message or result.warnings: print(json.dumps({'status': result.status, 'message': result.message, 'warnings': result.warnings, 'details': result.details}, ensure_ascii=False), file=sys.stderr if result.exit_code else sys.stdout)\n"
        "    return result.exit_code\n",
        encoding='utf-8',
    )
    for rel, text in {
        'scripts/claude_hooks/policy/bash_policy.py': "def evaluate_command(cmd):\n    return type('D',(),{'allowed': True, 'status': 'PASS', 'reason': '', 'warnings': []})()\ndef is_read_only_command(cmd): return True\n",
        'scripts/claude_hooks/policy/config_policy.py': "def record_config_change(*args, **kwargs): return None\n",
        'scripts/claude_hooks/policy/session_context.py': "def handle_session_start(*args, **kwargs): return None\n",
        'scripts/claude_hooks/self_test.py': "def run_self_test(): return None\n",
        'scripts/quality/changed_files.py': "def write_base_commit_if_missing(*args, **kwargs): return None\n",
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


def write_payload(path: str | None = '.claude/agents/qwen-main-default.md') -> str:
    tool_input = {'file_path': path} if path is not None else {}
    return json.dumps(
        {'tool_name': 'Write', 'session_id': 'synthetic-session', 'tool_input': tool_input}
    )


def run_in_fixture(root: Path, command: list[str], payload: str) -> subprocess.CompletedProcess[str]:
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
        [sys.executable, '-m', 'scripts.claude_hooks.main', 'pre-write'],
        write_payload(),
    )

    assert result.returncode == 2
    assert 'OpenSpec guard BLOCK' in result.stderr


def test_codex_pre_write_blocks_protected_without_change(tmp_path: Path) -> None:
    copy_runtime_guard_fixture(tmp_path)

    result = run_in_fixture(tmp_path, ['bash', '.codex/hooks/pre_write_guard.sh'], write_payload())

    assert result.returncode == 2
    assert 'OpenSpec guard BLOCK' in result.stderr


def test_qoder_pre_write_blocks_protected_without_change(tmp_path: Path) -> None:
    copy_runtime_guard_fixture(tmp_path)

    result = run_in_fixture(tmp_path, ['bash', '.qoder/hooks/pre_write_guard.sh'], write_payload())

    assert result.returncode == 2
    assert 'OpenSpec guard BLOCK' in result.stderr
