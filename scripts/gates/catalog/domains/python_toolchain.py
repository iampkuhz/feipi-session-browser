"""负责声明 Python 工具链领域的 Gate；不负责运行 Python 工具。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.domains.session_pipeline import SCAN_SMOKE_TESTS
from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
    changed,
    command,
    python_check,
    recipe,
)

PYTHON_ENVIRONMENT_PATHS = ('scripts/pyproject.toml', 'scripts/uv.lock', 'scripts/.python-version')

GATES = (
    Gate(
        name='scriptToolchainQuality',
        description='检查 Python 格式、静态问题、依赖声明、安全与死代码。',
        trigger=changed(
            *PYTHON_ENVIRONMENT_PATHS,
            'scripts/**/*.py',
        ),
        target_presets=('gate-infrastructure',),
        recipe=recipe(
            80,
            165,
            command(
                'pythonFormat',
                '{python}',
                '-m',
                'ruff',
                'format',
                '--check',
                '--config',
                '{tool_config}',
                '.',
            ),
            command(
                'pythonLint',
                '{python}',
                '-m',
                'ruff',
                'check',
                '--config',
                '{tool_config}',
                '.',
            ),
            command(
                'pythonDependencyDeclarations',
                '{python}',
                '-m',
                'deptry',
                '--config',
                '{tool_config}',
                'scripts',
            ),
            command(
                'pythonSourceSecurity',
                '{python}',
                '-m',
                'bandit',
                '-q',
                '-c',
                '{tool_config}',
                '-r',
                'scripts',
                '--severity-level',
                'high',
            ),
            command(
                'pythonDeadCode',
                '{python}',
                '-m',
                'vulture',
                '--config',
                '{tool_config}',
            ),
        ),
    ),
    Gate(
        name='bashSyntax',
        description='逐一解析 Shell 脚本，不执行脚本内容。',
        trigger=changed('scripts/**/*.sh'),
        target_presets=('gate-infrastructure',),
        recipe=recipe(
            10,
            20,
            command(
                'bashSyntax',
                'bash',
                '-ec',
                'for script; do bash -n -- "$script"; done',
                'bashSyntax',
                append_globs=('scripts/**/*.sh',),
            ),
        ),
    ),
    Gate(
        name='gateFrameworkTests',
        description='运行受影响的 Pytest 契约；共享或未知输入使用完整发现。',
        trigger=changed(
            *PYTHON_ENVIRONMENT_PATHS,
            'scripts/gates/**/*.py',
            'scripts/harness/**/*.py',
            'scripts/harness/java_env.sh',
            'scripts/openspec/**/*.py',
            'scripts/tests/**/*.py',
        ),
        target_presets=('gate-infrastructure',),
        recipe=recipe(
            60,
            180,
            command(
                'gateFrameworkTests',
                '{python}',
                '-m',
                'pytest',
                '-c',
                '{tool_config}',
                '--rootdir',
                '{repo_root}',
                '-W',
                'error',
                *(f'--ignore={path}' for path in SCAN_SMOKE_TESTS),
                'scripts/tests',
                required_paths=('scripts/tests',),
            ),
        ),
    ),
    Gate(
        name='pythonDependencyAudit',
        description='审计 Python 锁定依赖中的已知漏洞。',
        trigger=changed(
            'scripts/pyproject.toml',
            'scripts/uv.lock',
        ),
        target_presets=('gate-infrastructure',),
        recipe=recipe(
            60,
            120,
            python_check(
                'pythonDependencyAudit',
                'repository.python-dependency-audit',
                '--root',
                '{repo_root}',
            ),
        ),
    ),
)
