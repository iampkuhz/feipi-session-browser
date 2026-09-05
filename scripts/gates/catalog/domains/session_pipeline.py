"""负责声明 Session 扫描管线领域的 Gate；不负责运行扫描命令。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
    changed,
    gradle_task,
    recipe,
    scan_smoke,
)

GATES = (
    Gate(
        name='scanCommandSmoke',
        description='验证 session-browser scan 命令与发行 CLI 的进程级契约。',
        trigger=changed(
            'scripts/session-browser.sh',
            'java/app-cli/**',
            'java/scan-engine/**',
            'java/sources/**',
            'java/index-store-sqlite/**',
            'scripts/gates/checks/**',
            'scripts/tests/script_commands/**',
        ),
        target_presets=('session-pipeline',),
        recipe=recipe(
            90,
            180,
            scan_smoke(
                'scanCommandSmoke',
                ('scripts/tests/script_commands/test_session_browser_scan_smoke.py',),
                (':java:app-cli:installDist',),
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
