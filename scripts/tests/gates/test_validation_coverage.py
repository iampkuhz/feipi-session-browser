"""最终根 check 承接产品测试证明，不删除零跳过或模块 check。"""

from pathlib import Path

from scripts.gates.catalog import gate_by_name

ROOT = Path(__file__).resolve().parents[3]


def test_final_root_check_contains_product_test_and_all_module_checks() -> None:
    root = (ROOT / 'java/build.gradle.kts').read_text()
    launcher = (ROOT / 'scripts/session-browser.sh').read_text()
    step = gate_by_name('javaBuildVerification').recipe.steps[0]
    assert step.tasks == ('check',)
    assert 'dependsOn(verifyNoSkippedJavaTests)' in root
    assert 'dependsOn(":java:tests:quality-gates:runJavaQualityGates")' in root
    assert 'dependsOn(leafSubprojects.map { "${it.path}:check" })' in root
    assert 'sub.tasks.names.takeIf { "test" in it }' in root
    assert 'exec ./java/gradlew -p java verifyNoSkippedJavaTests' in launcher
    assert '-x' not in step.args
