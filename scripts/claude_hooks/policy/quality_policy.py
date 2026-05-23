from __future__ import annotations

from ..classify import required_quality_targets
from ..evidence import read_changed_files
from ..paths import RepoPaths


# 01. 根据 changed-files 推导目标
def infer_required_targets(paths: RepoPaths) -> list[str]:
    rows = read_changed_files(paths)
    files = [str(row.get("file") or "") for row in rows if row.get("requiresQualityGate")]
    return required_quality_targets(files)


# 02. 下一步命令提示
def command_for_target(target: str, change_id: str) -> str:
    return f"python3 scripts/quality/run_quality_gate.py --target {target} --change-id {change_id}"
