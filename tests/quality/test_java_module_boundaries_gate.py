"""Java module boundary gate 路由与命令契约。"""

from pathlib import Path

from scripts.gates import cli
from scripts.gates import executor as gate_executor
from scripts.gates.planner import classify_path, required_gates_for_target


def test_java_targets_include_module_boundaries_and_pmd_reuse_gates() -> None:
    """java-src/java-build 都必须运行模块边界与复用门禁。"""
    java_src = required_gates_for_target('java-src')
    java_build = required_gates_for_target('java-build')

    for gates in (java_src, java_build):
        assert 'javaModuleBoundaries' in gates
        assert 'reuseStandardCpd' in gates
        assert 'reuseAnalyzeIncremental' in gates


def test_java_architecture_config_triggers_java_build() -> None:
    """模块边界配置变更必须触发 java-build target。"""
    classification = classify_path('config/architecture/java-modules.yaml')

    assert classification.quality_target == 'java-build'
    assert classification.allowed_by_default is True


def test_reuse_policy_config_triggers_java_build() -> None:
    """复用策略配置变更必须触发 java-build target。"""
    classification = classify_path('config/reuse-policy/policy.json')

    assert classification.quality_target == 'java-build'
    assert classification.allowed_by_default is True


def test_pmd_reuse_rules_include_duplicate_delegating_method_scan() -> None:
    """PMD 规则集必须保留 addInsert 类重复委托函数扫描。"""
    pmd_rules = Path('config/pmd/pmd.xml').read_text(encoding='utf-8')

    assert 'FeipiDuplicateDelegatingMethods' in pmd_rules


def test_pmd_config_triggers_java_build() -> None:
    """PMD 规则集变更必须触发 java-build target。"""
    classification = classify_path('config/pmd/pmd.xml')

    assert classification.quality_target == 'java-build'
    assert classification.allowed_by_default is True


def test_java_module_build_file_is_known_java_build_path() -> None:
    """子模块 build.gradle.kts 不应落入 unknown fail-closed 分支。"""
    classification = classify_path('java/data/build.gradle.kts')

    assert classification.category == 'java-build'
    assert classification.quality_target == 'java-build'


def test_java_module_boundaries_gate_command_uses_repo_script() -> None:
    """quality gate runner 应调用仓库内模块边界脚本。"""
    command = gate_executor.gate_command('javaModuleBoundaries', Path.cwd(), 'java-src')

    assert command[-1].endswith('scripts/checks/check_java_module_boundaries.py')


def test_reuse_standard_cpd_gate_command_uses_incremental_wrapper(
    tmp_path: Path, monkeypatch
) -> None:
    """reuseStandardCpd gate 必须调用默认增量 wrapper，而不是直接全量 Gradle task。"""
    monkeypatch.delenv('QUALITY_GATE_TIER', raising=False)
    runner = tmp_path / 'scripts' / 'checks' / 'run_reuse_standard_cpd.py'
    runner.parent.mkdir(parents=True)
    runner.write_text('#!/usr/bin/env python3\n', encoding='utf-8')

    command = gate_executor.gate_command('reuseStandardCpd', tmp_path, 'java-src')

    assert command
    assert command[1] == str(runner)
    assert '--mode' not in command


def test_gate_cli_can_resolve_active_change_id(tmp_path: Path) -> None:
    """Gate CLI 支持未显式传 --change-id 时读取 tmp/active_change.json。"""
    active_change = tmp_path / 'tmp' / 'active_change.json'
    active_change.parent.mkdir()
    active_change.write_text('{"change_id": "strengthen-java-reuse-analyzer"}', encoding='utf-8')

    assert cli.resolve_change_id(None, tmp_path) == 'strengthen-java-reuse-analyzer'
