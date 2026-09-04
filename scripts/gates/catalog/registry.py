"""负责汇总六个领域声明并提供 Gate 与 TargetPreset 唯一查询入口；不负责执行。

由 CLI、Planning 和 Maintenance 阶段调用。"""

from __future__ import annotations

from typing import Never

from scripts.gates.catalog.domains.agent_harness import GATES as AGENT_HARNESS_GATES
from scripts.gates.catalog.domains.java_build import GATES as JAVA_BUILD_GATES
from scripts.gates.catalog.domains.python_toolchain import GATES as PYTHON_TOOLCHAIN_GATES
from scripts.gates.catalog.domains.repository_rules import GATES as REPOSITORY_RULE_GATES
from scripts.gates.catalog.domains.session_pipeline import GATES as SESSION_PIPELINE_GATES
from scripts.gates.catalog.domains.web_interface import GATES as WEB_INTERFACE_GATES
from scripts.gates.catalog.gate_contracts import Gate, GateCatalog, TargetPreset
from scripts.gates.catalog.validation import validate_gate_catalog

TARGET_PRESETS = (
    TargetPreset('gate-infrastructure', '人工运行 Gate 框架与 Python 工具链相关 Gate。'),
    TargetPreset('agent-governance', '人工运行 Agent、Skill、Harness 与 OpenSpec 治理 Gate。'),
    TargetPreset('web-interface', '人工运行 Web 页面、静态资源与浏览器交互 Gate。'),
    TargetPreset('java-source', '人工运行 Java 源码与测试质量 Gate。'),
    TargetPreset('java-build', '人工运行 Gradle 构建与 Java 工程配置 Gate。'),
    TargetPreset('session-pipeline', '人工运行扫描命令、发行 CLI 与样本集成 Gate。'),
)

GATES = (
    *PYTHON_TOOLCHAIN_GATES,
    *REPOSITORY_RULE_GATES,
    *AGENT_HARNESS_GATES,
    *WEB_INTERFACE_GATES,
    *JAVA_BUILD_GATES,
    *SESSION_PIPELINE_GATES,
)

CATALOG = GateCatalog(TARGET_PRESETS, GATES)


def gate_by_name(name: str) -> Gate:
    """按唯一公开 ID 查找 Gate，未知名称 fail-closed。"""

    for gate in GATES:
        if gate.name == name:
            return gate
    return _unknown('gate', name)


def target_preset_by_name(name: str) -> TargetPreset:
    """按唯一公开 ID 查找人工 TargetPreset，未知名称 fail-closed。"""

    for preset in TARGET_PRESETS:
        if preset.name == name:
            return preset
    return _unknown('target preset', name)


def _unknown(kind: str, name: str) -> Never:
    label = 'Gate' if kind == 'gate' else 'TargetPreset'
    raise ValueError(f'unknown {label}: {name}')


validate_gate_catalog(CATALOG)
