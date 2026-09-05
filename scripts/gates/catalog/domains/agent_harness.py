"""负责声明 Agent 与 Harness 治理领域的 Gate；不负责运行治理检查。

由 Catalog registry 调用并汇总这些声明。"""

from scripts.gates.catalog.gate_contracts import Gate
from scripts.gates.catalog.recipe_dsl import (
    changed,
    command,
    python_check,
    recipe,
)

GATES = (
    Gate(
        name='agentConfigurationPolicy',
        description='统一检查 Agent 运行配置与维护文档政策。',
        trigger=changed(
            'AGENTS.md',
            '.claude/CLAUDE.md',
            '.agents/**',
            '.claude/**',
            '.codex/**',
            '.qoder/**',
            'skills/**',
            'harness/**',
            'scripts/harness/**/*.py',
            'scripts/harness/**/*.sh',
            'scripts/gates/checks/agent/**',
            'scripts/gates/checks/check_registry.py',
        ),
        target_presets=('agent-governance',),
        recipe=recipe(
            30,
            60,
            python_check(
                'agentEntrypoints',
                'agent.entrypoints',
            ),
            python_check(
                'agentDocumentation',
                'agent.documentation',
            ),
        ),
    ),
    Gate(
        name='governanceLayoutValidation',
        description='统一验证 Skill registry、Harness 结构与 OpenSpec 布局。',
        trigger=changed(
            'harness/skill-registry.yaml',
            'skills/**',
            '.agents/skills/**',
            '.claude/skills/**',
            '.codex/skills/**',
            'scripts/gates/checks/agent/check_skill_registry.py',
            'harness/**',
            'scripts/harness/**/*.py',
            'openspec/**',
        ),
        target_presets=('agent-governance',),
        recipe=recipe(
            24,
            45,
            python_check(
                'skillRegistry',
                'agent.skill-registry',
            ),
            command(
                'harnessStructure',
                '{python}',
                'scripts/harness/validate_harness_structure.py',
            ),
            command(
                'openspecLayout',
                '{python}',
                'scripts/openspec/validate_layout.py',
            ),
        ),
    ),
)
