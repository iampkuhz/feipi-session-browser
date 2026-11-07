import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from scripts.gates.catalog.registry import gate_by_name
from scripts.openspec.validate_layout import validate

# 独立冻结原两个 validator 的契约并集，避免只依赖生产常量而漏测。
LEGACY_REQUIRED_PATHS = (
    '.claude/CLAUDE.md',
    'AGENTS.md',
    '.claude/settings.json',
    '.claude/commands',
    '.claude/agents',
    'openspec/specs',
    'openspec/changes',
    'openspec/schemas',
    'openspec/templates',
    'harness/README.md',
    'harness/manifest.yaml',
    'scripts/openspec',
    'scripts/gates/checks',
    'scripts/session-browser.sh',
    'harness/agent-policy.manifest.yaml',
    'harness/skill-registry.yaml',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'scripts/openspec/validate_layout.py',
)


def test_each_legacy_required_path_is_checked(tmp_path: Path) -> None:
    for index, missing in enumerate(LEGACY_REQUIRED_PATHS):
        case_root = tmp_path / str(index)
        for rel in LEGACY_REQUIRED_PATHS:
            if rel == missing or rel.startswith(missing + '/'):
                continue
            target = case_root / rel
            if rel.endswith(('.md', '.yaml', '.py', '.json')):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            else:
                target.mkdir(parents=True, exist_ok=True)
        assert any(missing in error for error in validate(case_root)), missing


def _create_complete_layout(root: Path) -> None:
    """创建满足冻结路径契约的最小目录树。"""
    for rel in LEGACY_REQUIRED_PATHS:
        target = root / rel
        if rel.endswith(('.md', '.yaml', '.py', '.json')):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        else:
            target.mkdir(parents=True, exist_ok=True)


def _run_layout(root: Path) -> subprocess.CompletedProcess[str]:
    """通过真实命令行入口运行 layout validator。"""
    script = Path(__file__).resolve().parents[2] / 'openspec' / 'validate_layout.py'
    return subprocess.run(
        [sys.executable, str(script)], cwd=root, capture_output=True, text=True, check=False
    )


def test_layout_cli_passes_complete_layout(tmp_path: Path) -> None:
    _create_complete_layout(tmp_path)
    result = _run_layout(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'repo structure ok' in result.stdout


def test_non_archive_change_requires_proposal_and_tasks(tmp_path: Path) -> None:
    change = tmp_path / 'openspec/changes/live'
    change.mkdir(parents=True)
    errors = validate(tmp_path)
    assert any('proposal.md missing' in error for error in errors)
    assert any('tasks.md missing' in error for error in errors)


def test_archive_change_is_exempt(tmp_path: Path) -> None:
    (tmp_path / 'openspec/changes/archive/old').mkdir(parents=True)
    assert not any('proposal.md missing' in error for error in validate(tmp_path))


def test_specs_and_changes_must_be_directories(tmp_path: Path) -> None:
    for name in ('specs', 'changes'):
        root = tmp_path / name
        _create_complete_layout(root)
        directory = root / 'openspec' / name
        directory.rmdir()
        directory.touch()
        result = _run_layout(root)
        assert result.returncode == 1, result.stdout + result.stderr
        assert f'openspec/{name} is not a directory' in result.stdout


def test_dangling_symlink_is_reported_as_missing(tmp_path: Path) -> None:
    target = tmp_path / LEGACY_REQUIRED_PATHS[0]
    target.parent.mkdir(parents=True)
    target.symlink_to(target.parent / 'absent')
    assert any(LEGACY_REQUIRED_PATHS[0] in error for error in validate(tmp_path))


def test_regular_file_change_entry_is_ignored(tmp_path: Path) -> None:
    changes = tmp_path / 'openspec/changes'
    changes.mkdir(parents=True)
    (changes / 'not-a-change').touch()
    assert not any('not-a-change' in error for error in validate(tmp_path))


def test_active_change_cli_fails_when_specs_are_missing(tmp_path: Path) -> None:
    change = tmp_path / 'openspec/changes/missing-specs'
    change.mkdir(parents=True)
    for name in ('proposal.md', 'tasks.md'):
        (change / name).write_text('# test\n', encoding='utf-8')
    script = Path(__file__).resolve().parents[2] / 'openspec' / 'validate_active_change.py'
    result = subprocess.run(
        [sys.executable, str(script), '--change-id', 'missing-specs'],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert 'Missing directory: openspec/changes/missing-specs/specs/' in result.stdout


def test_create_active_change_cli_uses_templates_and_is_idempotent(tmp_path: Path) -> None:
    templates = tmp_path / 'skills/authoring/feipi-openspec-orchestrate-change/templates'
    templates.mkdir(parents=True)
    source_templates = (
        Path(__file__).resolve().parents[3]
        / 'skills/authoring/feipi-openspec-orchestrate-change/templates'
    )
    for name in ('proposal.md', 'design.md', 'tasks.md', 'spec.md'):
        shutil.copyfile(source_templates / name, templates / name)
    expected_proposal = (
        (templates / 'proposal.md')
        .read_text(encoding='utf-8')
        .replace('<change-id>', 'cli-template-check')
    )
    expected_tasks = (
        (templates / 'tasks.md')
        .read_text(encoding='utf-8')
        .replace('<change-id>', 'cli-template-check')
    )
    assert expected_tasks.count('- [ ]') == 1
    assert '## 任务 5' not in expected_tasks
    script = Path(__file__).resolve().parents[2] / 'openspec' / 'create_active_change.py'
    command = [sys.executable, str(script), '--change-id', 'cli-template-check', '--source', 'test']
    first = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    change = tmp_path / 'openspec/changes/cli-template-check'
    assert '<change-id>' not in (change / 'proposal.md').read_text(encoding='utf-8')
    assert not (change / 'design.md').exists()
    assert '<change-id>' not in (change / 'specs/spec.md').read_text(encoding='utf-8')
    assert (change / 'tasks.md').read_text(encoding='utf-8') == expected_tasks
    validator = script.with_name('validate_active_change.py')
    result = subprocess.run(
        [sys.executable, str(validator), '--change-id', 'cli-template-check'],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (change / 'tasks.md').write_text('# completed custom task\n', encoding='utf-8')
    (templates / 'proposal.md').write_text('# changed template\n', encoding='utf-8')
    second = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert (change / 'proposal.md').read_text(encoding='utf-8') == expected_proposal
    assert (change / 'tasks.md').read_text(encoding='utf-8') == '# completed custom task\n'


def test_openspec_python_changes_trigger_layout_governance_gate() -> None:
    patterns = gate_by_name('governanceLayoutValidation').trigger.paths
    touched = (
        'scripts/openspec/validate_layout.py',
        'scripts/openspec/validate_active_change.py',
        'scripts/openspec/create_active_change.py',
        'scripts/openspec/new.py',
    )
    for path in touched:
        assert any(PurePosixPath(path).match(pattern) for pattern in patterns), path
