"""负责导出 Gate Catalog 阶段的公开契约与唯一 registry；不负责规划或执行。

由 CLI、Planning 和 Maintenance 阶段通过此入口调用 Catalog。"""

from scripts.gates.catalog.gate_contracts import (
    DurationExpectations,
    ExecutionMode,
    Gate,
    GateCatalog,
    GateRecipe,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
    TargetPreset,
    TriggerMode,
)
from scripts.gates.catalog.registry import (
    CATALOG,
    GATES,
    TARGET_PRESETS,
    gate_by_name,
    target_preset_by_name,
)
from scripts.gates.catalog.validation import validate_gate_catalog

__all__ = (
    'CATALOG',
    'GATES',
    'TARGET_PRESETS',
    'DurationExpectations',
    'ExecutionMode',
    'Gate',
    'GateCatalog',
    'GateRecipe',
    'GateTrigger',
    'RecipeStep',
    'RecipeStepKind',
    'TargetPreset',
    'TriggerMode',
    'gate_by_name',
    'target_preset_by_name',
    'validate_gate_catalog',
)
