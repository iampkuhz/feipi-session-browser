"""负责声明 Session 扫描管线领域的 Gate；不负责运行扫描命令。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
    JAVA_RUNTIME_BUILD_INPUTS,
    PRODUCT_EXECUTION_PATHS,
    changed,
    gradle_task,
    recipe,
    scan_smoke,
)

SCAN_SMOKE_TESTS = (
    'scripts/tests/script_commands/test_session_browser_serve_smoke.py',
    'scripts/tests/script_commands/test_session_browser_scan_smoke.py',
)

GATES = (
    Gate(
        name='scanCommandSmoke',
        description='验证 scan 命令及正常 serve 的进程归属、自动扫描与内容交付契约。',
        trigger=changed(
            *JAVA_RUNTIME_BUILD_INPUTS,
            'java/*/src/main/java/**',
            'java/*/src/main/kotlin/**',
            'java/app-cli/src/main/resources/**',
            'java/index-store-sqlite/src/main/resources/**',
            'java/validation/src/main/resources/**',
            'java/web/src/main/resources/templates/**',
            *SCAN_SMOKE_TESTS,
            'scripts/tests/conftest.py',
            *PRODUCT_EXECUTION_PATHS,
        ),
        target_presets=('session-pipeline',),
        recipe=recipe(
            90,
            180,
            scan_smoke(
                'scanCommandSmoke',
                SCAN_SMOKE_TESTS,
                (),
                '-n',
                '0',
                '-q',
                '-W',
                'error',
            ),
        ),
    ),
    Gate(
        name='sessionSampleContracts',
        description='用合成 Session 样本验证解析、标准化与契约集成。',
        trigger=changed(
            'java/tests/fixtures/session_samples/**',
            'java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**',
            'java/sources/**',
            'java/normalization-engine/**',
            'java/scan-engine/src/main/java/com/feipi/session/browser/scan/artifact/**',
            'java/tests/contracts/src/test/java/com/feipi/session/browser/contracttest/sample/**',
        ),
        target_presets=('session-pipeline',),
        recipe=recipe(
            90,
            240,
            gradle_task(
                'sessionSampleContracts',
                ':java:tests:contracts:sampleIntegrationTest',
            ),
        ),
    ),
)
