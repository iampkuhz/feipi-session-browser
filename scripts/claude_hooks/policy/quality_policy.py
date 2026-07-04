"""提供 quality policy 脚本能力。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..classify import required_quality_targets
from ..evidence import read_changed_files

if TYPE_CHECKING:
    from ..paths import RepoPaths


# 维护推断 必需 targets。
def infer_required_targets(paths: RepoPaths) -> list[str]:
    """参数：
        paths: Repository 运行time 路径 that locate changed-文件 evidence。

    返回：
        结果列表。
    """
    rows = read_changed_files(paths)
    files = [str(row.get('file') or '') for row in rows if row.get('requiresQualityGate')]
    return required_quality_targets(files)


# 维护命令 target。
def command_for_target(target: str, change_id: str) -> str:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        change_id: 当前 OpenSpec change id。

    返回：
        指定 target 的命令字符串。
    """
    return f'python3 scripts/quality/run_quality_gate.py --target {target} --change-id {change_id}'
