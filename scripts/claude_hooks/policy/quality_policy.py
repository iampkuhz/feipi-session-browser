"""Infer required quality gates from Claude hook changed-file evidence.

Stop hooks and diagnostics use this module after write hooks have populated
``changed-files.jsonl``. It maps touched files to quality targets and formats the command
users should run; it does not execute gates itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..classify import required_quality_targets
from ..evidence import read_changed_files

if TYPE_CHECKING:
    from ..paths import RepoPaths


# 01. 根据 changed-files 推导目标
def infer_required_targets(paths: RepoPaths) -> list[str]:
    """Infer quality targets required by changed files in the current session.

    Args:
        paths: Repository runtime paths that locate changed-file evidence.

    Returns:
        Ordered, de-duplicated quality target names for files marked as requiring gates.
    """
    rows = read_changed_files(paths)
    files = [str(row.get('file') or '') for row in rows if row.get('requiresQualityGate')]
    return required_quality_targets(files)


# 02. 下一步命令提示
def command_for_target(target: str, change_id: str) -> str:
    """Format the remediation command for one required quality target.

    Args:
        target: Quality target inferred from changed-file evidence.
        change_id: Active OpenSpec change id used by gate evidence.

    Returns:
        Command string that runs the corresponding quality gate for the active change.
    """
    return f'python3 scripts/quality/run_quality_gate.py --target {target} --change-id {change_id}'
