"""双模式 Gate Catalog 的严格 schema 与不可变模型契约。"""

from __future__ import annotations

import copy
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml
from scripts.gates.catalog import CATALOG, _load_catalog, gate_by_name, target_by_name
from scripts.gates.model import ExecutionMode, RunKind, TriggerMode

GATE_FILES = tuple(f'gates/{path.name}' for path in sorted(Path('config/gates').glob('*.yaml')))


@pytest.fixture
def catalog_tree(tmp_path: Path) -> Path:
    """复制当前 Catalog，让失败用例只修改隔离配置。"""

    root = tmp_path / 'gates.yaml'
    shutil.copy2('config/gates.yaml', root)
    fragment_dir = tmp_path / 'gates'
    fragment_dir.mkdir()
    for source in Path('config/gates').glob('*.yaml'):
        shutil.copy2(source, fragment_dir / source.name)
    return root


def _read(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def _write(path: Path, value: object) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding='utf-8')


def _first_gate(catalog_tree: Path) -> tuple[Path, dict[str, object], dict[str, object]]:
    root = _read(catalog_tree)
    fragment = catalog_tree.parent / root['gate_files'][0]  # type: ignore[index]
    data = _read(fragment)
    return fragment, data, data['gates'][0]  # type: ignore[index,return-value]


def test_current_catalog_has_stable_inventory_and_all_six_run_kinds() -> None:
    assert tuple(target.name for target in CATALOG.targets) == (
        'python-standard',
        'harness',
        'session-detail',
        'java-src',
        'java-build',
        'scan-script-smoke',
    )
    assert len(CATALOG.gates) == 41
    assert tuple(gate.name for gate in CATALOG.gates[:3]) == (
        'pythonFormat',
        'pythonLint',
        'pythonHarnessTests',
    )
    assert tuple(gate.name for gate in CATALOG.gates[-3:]) == (
        'javaApiSnapshot',
        'scanScriptSmoke',
        'sessionSamples',
    )
    assert {gate.run.kind for gate in CATALOG.gates} == set(RunKind)
    assert len(CATALOG.path_rules) == 18


def test_every_gate_has_five_field_model_and_two_complete_timing_profiles() -> None:
    for gate in CATALOG.gates:
        assert gate.name and gate.description
        assert gate.trigger.mode in TriggerMode
        if gate.trigger.mode is TriggerMode.CHANGED:
            assert gate.trigger.paths
        else:
            assert not gate.trigger.paths
        for mode in ExecutionMode:
            profile = gate.run.profile_for(mode)
            assert profile.target_seconds > 0
            assert profile.timeout_seconds >= profile.target_seconds


def test_same_as_copies_execution_only_and_keeps_explicit_full_timing() -> None:
    gate = gate_by_name('pythonFormat')
    incremental = gate.run.incremental
    full = gate.run.full
    assert full.argv == incremental.argv
    assert full is not incremental
    assert full.target_seconds > 0
    assert full.timeout_seconds >= full.target_seconds
    assert gate.run.profile_for('incremental') is incremental
    assert gate.run.profile_for('full') is full


def test_lookup_and_models_are_strict_and_frozen() -> None:
    assert target_by_name('java-src').description.startswith('人工运行')
    with pytest.raises(ValueError, match='Unknown quality gate'):
        gate_by_name('missing')
    with pytest.raises(ValueError, match='Unknown quality target'):
        target_by_name('missing')
    with pytest.raises(FrozenInstanceError):
        CATALOG.gates = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    'old_key',
    [
        'gate_defaults',
        'target_triggers',
        'minimum_tier',
        'timeout',
        'changed_files',
        'network_failure',
        'policy',
        'inputs',
    ],
)
def test_old_root_or_gate_fields_are_rejected(catalog_tree: Path, old_key: str) -> None:
    if old_key in {'gate_defaults', 'target_triggers'}:
        root = _read(catalog_tree)
        root[old_key] = {}
        _write(catalog_tree, root)
    else:
        fragment, data, gate = _first_gate(catalog_tree)
        gate[old_key] = 'legacy'
        _write(fragment, data)
    with pytest.raises(ValueError, match='unexpected='):
        _load_catalog(catalog_tree)


def test_target_rule_object_is_rejected(catalog_tree: Path) -> None:
    fragment, data, gate = _first_gate(catalog_tree)
    gate['targets'] = [{'name': 'python-standard', 'order': 0, 'patterns': ['scripts/**']}]
    _write(fragment, data)
    with pytest.raises(ValueError):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('location', ['root', 'target', 'path-rule', 'gate', 'trigger', 'run'])
def test_required_fields_are_rejected_at_every_level(catalog_tree: Path, location: str) -> None:
    root = _read(catalog_tree)
    fragment, data, gate = _first_gate(catalog_tree)
    if location == 'root':
        del root['path_rules']
        _write(catalog_tree, root)
    elif location == 'target':
        del root['targets'][0]['description']  # type: ignore[index]
        _write(catalog_tree, root)
    elif location == 'path-rule':
        del root['path_rules'][0]['patterns']  # type: ignore[index]
        _write(catalog_tree, root)
    elif location == 'gate':
        del gate['description']
        _write(fragment, data)
    elif location == 'trigger':
        del gate['trigger']['paths']  # type: ignore[index]
        _write(fragment, data)
    else:
        del gate['run']['full']  # type: ignore[index]
        _write(fragment, data)
    with pytest.raises(ValueError, match='missing='):
        _load_catalog(catalog_tree)


def test_always_trigger_forbids_paths(catalog_tree: Path) -> None:
    fragment, data, gate = _first_gate(catalog_tree)
    gate['trigger'] = {'mode': 'always', 'paths': ['scripts/**']}
    _write(fragment, data)
    with pytest.raises(ValueError, match='unexpected='):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize(
    ('mutation', 'message'),
    [
        ({'same_as': 'full', 'target_seconds': 1, 'timeout_seconds': 2}, 'same_as'),
        (
            {
                'same_as': 'incremental',
                'argv': ['tool'],
                'target_seconds': 1,
                'timeout_seconds': 2,
            },
            'unexpected=',
        ),
        ({'target_seconds': 10, 'timeout_seconds': 9, 'argv': ['tool']}, '>='),
    ],
)
def test_same_as_and_timing_fail_closed(
    catalog_tree: Path, mutation: dict[str, object], message: str
) -> None:
    fragment, data, gate = _first_gate(catalog_tree)
    gate['run']['full'] = mutation  # type: ignore[index]
    _write(fragment, data)
    with pytest.raises(ValueError, match=message):
        _load_catalog(catalog_tree)


def test_unknown_target_and_duplicate_gate_are_rejected(catalog_tree: Path) -> None:
    fragment, data, gate = _first_gate(catalog_tree)
    gate['targets'] = ['missing-target']
    data['gates'].append(copy.deepcopy(gate))  # type: ignore[index]
    _write(fragment, data)
    with pytest.raises(ValueError):
        _load_catalog(catalog_tree)


def test_unused_target_is_rejected(catalog_tree: Path) -> None:
    root = _read(catalog_tree)
    root['targets'].append({'name': 'unused', 'description': '人工运行未绑定的 Gate。'})  # type: ignore[index]
    _write(catalog_tree, root)
    with pytest.raises(ValueError, match='selects no Gate'):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize(
    ('mutation', 'message'),
    [
        (('target-description', 'not Chinese.'), 'Chinese sentence'),
        (('path-risk', 'urgent'), 'invalid value'),
        (('required-path', '../outside'), 'repository-relative paths'),
        (('append-glob', '/absolute/**'), 'repository-relative globs'),
    ],
)
def test_human_text_and_repository_paths_are_strict(
    catalog_tree: Path, mutation: tuple[str, str], message: str
) -> None:
    kind, value = mutation
    root = _read(catalog_tree)
    if kind == 'target-description':
        root['targets'][0]['description'] = value  # type: ignore[index]
        _write(catalog_tree, root)
    elif kind == 'path-risk':
        root['path_rules'][0]['risk'] = value  # type: ignore[index]
        _write(catalog_tree, root)
    else:
        fragment = catalog_tree.parent / 'gates/python-tooling.yaml'
        data = _read(fragment)
        profile = data['gates'][2]['run']['incremental']  # type: ignore[index]
        profile['required_paths' if kind == 'required-path' else 'append_globs'] = [value]
        _write(fragment, data)
    with pytest.raises(ValueError, match=message):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('syntax', ['anchor', 'duplicate', 'merge'])
def test_yaml_indirection_and_duplicate_keys_are_rejected(catalog_tree: Path, syntax: str) -> None:
    source = catalog_tree.read_text(encoding='utf-8')
    if syntax == 'anchor':
        source = source.replace('targets:', 'targets: &targets', 1)
    elif syntax == 'duplicate':
        source += '\ntargets: []\n'
    else:
        source += '\n<<: {}\n'
    catalog_tree.write_text(source, encoding='utf-8')
    with pytest.raises(ValueError):
        _load_catalog(catalog_tree)


def test_fragments_are_unique_canonical_and_cannot_escape(catalog_tree: Path) -> None:
    root = _read(catalog_tree)
    for bad in ([], [*GATE_FILES, GATE_FILES[0]], ['/tmp/gates.yaml'], ['gates/../bad.yaml']):
        changed = copy.deepcopy(root)
        changed['gate_files'] = bad
        _write(catalog_tree, changed)
        with pytest.raises(ValueError):
            _load_catalog(catalog_tree)
