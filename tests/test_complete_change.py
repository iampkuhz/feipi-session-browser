import ast
from pathlib import Path

import pytest
from scripts.harness import complete_change

ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_entrypoint_only_delegates_to_change_controller(monkeypatch, tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    monkeypatch.setattr(
        complete_change,
        'collect_manifest',
        lambda _repo: type('Manifest', (), {'paths': ('owned.txt',), 'manifest_hash': 'hash'})(),
    )
    calls = []
    monkeypatch.setattr(complete_change, 'change_main', lambda argv: calls.append(argv) or 0)

    assert (
        complete_change.main(
            [
                '--repo-root',
                str(repo),
                '--run-id',
                'run-1',
                '--message',
                'chore: complete',
                '--file',
                'owned.txt',
            ]
        )
        == 0
    )
    assert calls[0][2] == 'on-stop'
    assert '--expect-manifest-hash' in calls[0]


def test_compatibility_file_list_is_only_an_exact_guard(monkeypatch, tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    monkeypatch.setattr(
        complete_change,
        'collect_manifest',
        lambda _repo: type('Manifest', (), {'paths': ('actual.txt',), 'manifest_hash': 'hash'})(),
    )
    with pytest.raises(SystemExit):
        complete_change.main(
            [
                '--repo-root',
                str(repo),
                '--run-id',
                'run-1',
                '--message',
                'chore: complete',
                '--file',
                'wrong.txt',
            ]
        )


def test_facade_has_no_gate_fixture_commit_or_integration_business():
    source = (ROOT / 'scripts/harness/complete_change.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    forbidden_calls = {'run_service', 'Popen', 'run_bounded', 'update_ref', 'commit', 'merge'}
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not (called & forbidden_calls)
    assert len(source.splitlines()) < 70
