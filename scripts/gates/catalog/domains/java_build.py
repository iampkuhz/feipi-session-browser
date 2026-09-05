"""负责声明 Java 构建与源码质量领域的 Gate；不负责启动 Gradle。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
    changed,
    gradle_task,
    recipe,
)

GATES = (
    Gate(
        name='javaBuildVerification',
        description='运行 Java 编译、测试和标准源码规则。',
        trigger=changed(
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
            'java/**/src/main/kotlin/**/*.kt',
            'java/**/src/test/kotlin/**/*.kt',
            '**/*.java',
            'java/gradle/config/architecture/java-modules.yaml',
            'scripts/gates/config/technical-terms.json',
            'java/gradle/build-logic/**',
            'java/gradle/**',
            'java/build.gradle.kts',
            'java/settings.gradle.kts',
            'java/**/build.gradle.kts',
            'java/gradle.properties',
            'java/gradlew',
            'java/gradlew.bat',
            'java/*.lockfile',
        ),
        target_presets=('java-source', 'java-build'),
        recipe=recipe(
            240,
            600,
            gradle_task(
                'javaBuildVerification',
                'check',
                '--parallel',
                '--build-cache',
            ),
        ),
    ),
    Gate(
        name='javaDuplicationAudit',
        description='使用 CPD 检查 Java 生产源码中的重复实现。',
        trigger=changed(
            'java/**/src/main/java/**/*.java',
            'java/gradle/config/reuse-policy/**',
            'java/**/build.gradle.kts',
            'java/settings.gradle.kts',
            'java/build.gradle.kts',
        ),
        target_presets=('java-source', 'java-build'),
        recipe=recipe(
            180,
            600,
            gradle_task(
                'reuseStandardCpd',
                'reuseStandardCpd',
            ),
        ),
    ),
)
