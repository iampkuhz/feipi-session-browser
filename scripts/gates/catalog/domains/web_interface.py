"""负责声明 Web 静态资源与浏览器领域的 Gate；不负责启动浏览器测试。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
    JAVA_RUNTIME_BUILD_INPUTS,
    PRODUCT_EXECUTION_PATHS,
    changed,
    gradle_task,
    java_rule,
    playwright,
    recipe,
)

GATES = (
    Gate(
        name='webStaticRules',
        description='统一检查 Web 模板、脚本、静态资源与 CSS 源码政策。',
        trigger=changed(
            'java/web/src/main/resources/**',
            'java/tests/quality-gates/**',
            'java/tests/quality-gates/config/web-quality-baselines.json',
            'java/tests/**/*.js',
            'scripts/**/*.js',
            'scripts/gates/catalog/domains/web_interface.py',
            'scripts/gates/catalog/recipe_dsl.py',
            'scripts/gates/execution/command_adapter.py',
        ),
        target_presets=('web-interface', 'gate-infrastructure', 'java-source'),
        recipe=recipe(
            90,
            180,
            java_rule(
                'webSourceRules',
                'raw-innerhtml',
                'layout-inline-style',
                'template-contract',
                'static-resource-contract',
                'css-ownership',
            ),
        ),
    ),
    Gate(
        name='webResourceContracts',
        description='运行 Java Web 模板、CSS 与 JavaScript 的资源契约测试。',
        trigger=changed(
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
        ),
        target_presets=('web-interface', 'java-source'),
        recipe=recipe(
            60,
            180,
            gradle_task(
                'webResourceContracts',
                ':java:web:test',
            ),
        ),
    ),
    Gate(
        name='browserTests',
        description='用 Playwright 完整发现并验证页面视觉、布局与交互契约。',
        trigger=changed(
            'java/tests/playwright/**',
            'java/tests/fixtures/**',
            'java/*/src/main/**',
            *JAVA_RUNTIME_BUILD_INPUTS,
            *PRODUCT_EXECUTION_PATHS,
        ),
        target_presets=('web-interface',),
        recipe=recipe(
            180,
            480,
            playwright('browserTests', (), '--workers={playwright_workers}'),
        ),
    ),
)
