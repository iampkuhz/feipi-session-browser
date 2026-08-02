"""当前 Gate catalog 的 strict schema 与 typed inventory contract。"""

import copy
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml
from scripts.gates.catalog import CATALOG, _load_catalog, gate_by_name
from scripts.gates.model import ChangedFilesInput, MinimumTier, RunKind
from scripts.gates.planner import gates_for_tier, validate_catalog

GATE_FILES = (
    'gates/python-tooling.yaml',
    'gates/repository-safety.yaml',
    'gates/harness-governance.yaml',
    'gates/web-quality.yaml',
    'gates/java-quality.yaml',
    'gates/product-smoke.yaml',
)


@pytest.fixture
def catalog_tree(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / 'config'
    shutil.copy2(source / 'gates.yaml', tmp_path / 'gates.yaml')
    shutil.copytree(source / 'gates', tmp_path / 'gates')
    return tmp_path / 'gates.yaml'


def _read(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding='utf-8'))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding='utf-8')


def _gate_with_run(catalog_tree: Path, run_kind: str) -> tuple[Path, dict, dict]:
    """返回包含指定 run kind 的分片、分片数据和 Gate 声明。"""
    for relative in GATE_FILES:
        path = catalog_tree.parent / relative
        data = _read(path)
        for gate in data['gates']:  # type: ignore[union-attr]
            if run_kind in gate['run']:
                return path, data, gate
    raise AssertionError(f'run kind not found: {run_kind}')


def test_current_inventory_is_typed_unique_and_exactly_42() -> None:
    validate_catalog()
    assert len(CATALOG.gates) == len({gate.name for gate in CATALOG.gates}) == 42
    assert CATALOG.gate_defaults.minimum_tier is MinimumTier.REQUIRED
    assert CATALOG.gate_defaults.timeout_seconds == 300
    assert CATALOG.gate_defaults.changed_files_input is ChangedFilesInput.NONE
    assert CATALOG.gate_defaults.network_failure == 'fail'


def test_root_schema_has_typed_defaults_and_generic_target_triggers(catalog_tree: Path) -> None:
    root = _read(catalog_tree)
    assert set(root) == {
        'gate_defaults',
        'targets',
        'gate_files',
        'path_rules',
        'target_triggers',
    }
    assert tuple(root['gate_files']) == GATE_FILES  # type: ignore[arg-type]
    assert _load_catalog(catalog_tree) == CATALOG


def test_gate_defaults_expand_and_same_value_override_is_rejected(catalog_tree: Path) -> None:
    gate = gate_by_name('pythonFormat')
    assert gate.minimum_tier is MinimumTier.REQUIRED
    assert gate.timeout_seconds == 300
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read(fragment)
    data['gates'][0]['timeout'] = 300  # type: ignore[index]
    _write(fragment, data)
    with pytest.raises(ValueError, match='redundantly overrides'):
        _load_catalog(catalog_tree)


def test_catalog_rejects_obsolete_version_field(catalog_tree: Path) -> None:
    root = _read(catalog_tree)
    root['version'] = 'obsolete-version'
    _write(catalog_tree, root)
    with pytest.raises(ValueError, match=r'unexpected=.*version'):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('lexical', ['yes', 'no', 'on', 'off', 'True', 'FALSE'])
def test_yaml_11_boolean_lexicals_are_not_accepted_as_booleans(
    catalog_tree: Path, lexical: str
) -> None:
    source = catalog_tree.read_text(encoding='utf-8')
    catalog_tree.write_text(
        source.replace('allowed: false', f'allowed: {lexical}', 1), encoding='utf-8'
    )
    with pytest.raises(ValueError, match='must be a boolean'):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('lexical', ['012', '0x12', '1_000', '+12', '1:20'])
def test_non_decimal_integer_lexicals_are_rejected(catalog_tree: Path, lexical: str) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    source = fragment.read_text(encoding='utf-8')
    fragment.write_text(source.replace('order: 0', f'order: {lexical}', 1), encoding='utf-8')
    with pytest.raises(ValueError, match='must be a non-negative integer'):
        _load_catalog(catalog_tree)


def test_python_check_rejects_glob_args_ignored_by_executor(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read(fragment)
    python_check = next(
        gate['run']['python-check']
        for gate in data['gates']  # type: ignore[union-attr]
        if 'python-check' in gate['run']
    )
    python_check['glob_args'] = ['tests/**/*.py']
    _write(fragment, data)
    with pytest.raises(ValueError, match=r'unexpected=.*glob_args'):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize(
    ('location', 'key', 'value'),
    [
        ('root', 'unknown', True),
        ('defaults', 'timeout', '300'),
        ('target', 'name', False),
        ('path', 'allowed', 'false'),
        ('trigger', 'patterns', 'scripts/**'),
        ('gate', 'timeout', True),
        ('gate-target', 'order', '0'),
        ('run', 'command', []),
    ],
)
def test_nested_schema_rejects_unknown_or_wrong_exact_types(
    catalog_tree: Path, location: str, key: str, value: object
) -> None:
    root = _read(catalog_tree)
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read(fragment)
    if location == 'root':
        root[key] = value
    elif location == 'defaults':
        root['gate_defaults'][key] = value  # type: ignore[index]
    elif location == 'target':
        root['targets'][0][key] = value  # type: ignore[index]
    elif location == 'path':
        root['path_rules'][0][key] = value  # type: ignore[index]
    elif location == 'trigger':
        root['target_triggers'][0][key] = value  # type: ignore[index]
    elif location == 'gate':
        data['gates'][0][key] = value  # type: ignore[index]
    elif location == 'gate-target':
        data['gates'][0]['targets'][0][key] = value  # type: ignore[index]
    else:
        data['gates'][0]['run'] = {key: value}  # type: ignore[index]
    _write(catalog_tree, root)
    _write(fragment, data)
    with pytest.raises((ValueError, TypeError)):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize(
    ('location', 'required_key'),
    [
        ('root', 'gate_defaults'),
        ('defaults', 'timeout'),
        ('target', 'name'),
        ('path', 'patterns'),
        ('trigger', 'target'),
        ('fragment', 'gates'),
        ('gate', 'description'),
        ('gate-target', 'order'),
    ],
)
def test_every_nested_object_rejects_missing_required_key(
    catalog_tree: Path, location: str, required_key: str
) -> None:
    root = _read(catalog_tree)
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read(fragment)
    if location == 'root':
        del root[required_key]
    elif location == 'defaults':
        del root['gate_defaults'][required_key]  # type: ignore[index]
    elif location == 'target':
        del root['targets'][0][required_key]  # type: ignore[index]
    elif location == 'path':
        del root['path_rules'][0][required_key]  # type: ignore[index]
    elif location == 'trigger':
        del root['target_triggers'][0][required_key]  # type: ignore[index]
    elif location == 'fragment':
        del data[required_key]
    elif location == 'gate':
        del data['gates'][0][required_key]  # type: ignore[index]
    else:
        del data['gates'][0]['targets'][0][required_key]  # type: ignore[index]
    _write(catalog_tree, root)
    _write(fragment, data)

    with pytest.raises(ValueError, match='missing='):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize(
    ('run_kind', 'required_key'),
    [
        ('command', 'argv'),
        ('python-check', 'check'),
        ('playwright', 'argv'),
        ('scan-smoke', 'prerequisite_tasks'),
        ('gradle-task', 'tasks'),
        ('java-rule', 'rules'),
    ],
)
def test_each_run_kind_rejects_missing_required_source(
    catalog_tree: Path, run_kind: str, required_key: str
) -> None:
    path, data, gate = _gate_with_run(catalog_tree, run_kind)
    del gate['run'][run_kind][required_key]
    _write(path, data)

    with pytest.raises(ValueError):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('required_key', ['path', 'argv'])
def test_optional_args_reject_missing_required_key(catalog_tree: Path, required_key: str) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read(fragment)
    gate = next(
        gate
        for gate in data['gates']  # type: ignore[union-attr]
        if gate['name'] == 'scriptCommentLanguage'
    )
    del gate['run']['python-check']['optional_args'][0][required_key]
    _write(fragment, data)

    with pytest.raises(ValueError, match='missing='):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('syntax', ['anchor', 'duplicate', 'merge'])
def test_yaml_inheritance_and_duplicate_keys_are_rejected(catalog_tree: Path, syntax: str) -> None:
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


def test_fragments_are_canonical_unique_and_cannot_escape(catalog_tree: Path) -> None:
    root = _read(catalog_tree)
    for bad in (
        [],
        [*GATE_FILES, GATE_FILES[0]],
        ['/tmp/gates.yaml', *GATE_FILES[1:]],
        ['gates/../python-tooling.yaml', *GATE_FILES[1:]],
    ):
        changed = copy.deepcopy(root)
        changed['gate_files'] = bad
        _write(catalog_tree, changed)
        with pytest.raises(ValueError):
            _load_catalog(catalog_tree)


def test_load_catalog_rejects_unknown_target_reference(catalog_tree: Path) -> None:
    root = _read(catalog_tree)
    root['path_rules'][0]['targets'] = ['unknown-target']  # type: ignore[index]
    _write(catalog_tree, root)

    with pytest.raises(ValueError, match='path rule target reference'):
        _load_catalog(catalog_tree)


def test_run_mapping_is_discriminated_and_java_task_is_adapter_owned() -> None:
    kinds = {gate.run.kind for gate in CATALOG.gates}
    assert kinds == set(RunKind)
    for gate in CATALOG.gates:
        if gate.run.kind is RunKind.JAVA_RULE:
            assert gate.run.java_rules
            assert not hasattr(gate.run, 'java_task')
    assert gate_by_name('pythonDependencyVulnerabilities').run.python == 'dev'
    assert gate_by_name('pythonDependencyVulnerabilities').minimum_tier is MinimumTier.FULL


def test_tier_membership_is_derived_from_minimum_tier() -> None:
    assert gate_by_name('bashSyntax').name in gates_for_tier('quick')
    assert gate_by_name('pythonFormat').name not in gates_for_tier('quick')
    assert gate_by_name('javaApiSnapshot').name not in gates_for_tier('required')
    assert gate_by_name('javaApiSnapshot').name in gates_for_tier('full')


def test_catalog_models_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        CATALOG.gates = ()  # type: ignore[misc]


def test_scan_smoke_inventory_preserves_historical_trigger_paths() -> None:
    trigger = next(item for item in CATALOG.target_triggers if item.target == 'scan-script-smoke')
    assert {
        'scripts/session-browser.sh',
        'scripts/checks/**',
        'java/app-cli/**',
        'java/scan-engine/**',
        'java/sources/**',
        'java/index-sqlite/**',
    } <= set(trigger.patterns)
    assert gate_by_name('scanScriptSmoke').run.kind is RunKind.SCAN_SMOKE


def test_java_targets_keep_reuse_and_pmd_rule_ownership() -> None:
    for target in ('java-src', 'java-build'):
        names = {gate.name for gate in CATALOG.gates if target in gate.targets}
        assert {'reuseStandardCpd', 'reuseAnalyzeIncremental'} <= names

    pmd_rules = Path('config/pmd/pmd.xml').read_text(encoding='utf-8')
    assert 'FeipiDuplicateDelegatingMethods' in pmd_rules
