"""负责声明 Web 静态资源与浏览器领域的 Gate；不负责启动浏览器测试。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
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
        ),
        target_presets=('web-interface', 'gate-infrastructure', 'java-source'),
        recipe=recipe(
            90,
            180,
            java_rule('rawInnerhtml', 'raw-innerhtml'),
            java_rule('layoutInlineStyle', 'layout-inline-style'),
            java_rule('templateContract', 'template-contract'),
            java_rule('staticCssContract', 'static-resource-contract'),
            java_rule('cssOwnership', 'css-ownership'),
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
        name='browserVisualTests',
        description='用 Playwright 验证主要页面、布局与视觉壳层契约。',
        trigger=changed(
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'java/tests/playwright/**',
        ),
        target_presets=('web-interface',),
        recipe=recipe(
            90,
            240,
            playwright(
                'browserVisualTests',
                (
                    'ui-contract.spec.ts',
                    'main-pages-visual.spec.ts',
                    'session-detail-layout',
                    'shell-states',
                    'dashboard-chart-coordinates',
                ),
                '--workers={playwright_workers}',
            ),
        ),
    ),
    Gate(
        name='browserBehaviorTests',
        description='用 Playwright 验证 Session 详情与列表页交互。',
        trigger=changed(
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'java/tests/playwright/**',
        ),
        target_presets=('web-interface',),
        recipe=recipe(
            90,
            240,
            playwright(
                'browserBehaviorTests',
                (
                    'session-detail.spec.js',
                    'session-detail-behavior-contracts.spec.js',
                    'sessions-list.spec.js',
                ),
                '--grep-invert',
                '100 轮',
                '--workers={playwright_workers}',
            ),
        ),
    ),
)
