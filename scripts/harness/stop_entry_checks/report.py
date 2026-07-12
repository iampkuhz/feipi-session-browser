"""Stop summary 写入与路径计算。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.claude_hooks import paths as runtime_paths


# 计算 runtime-report 的输出路径。
def runtime_report_path(
    repo_root: Path,
    identity: Any,
    change_id: str,
) -> Path:
    """参数：
        repo_root: 当前函数使用的输入参数。
        identity: 当前函数使用的输入参数。
        change_id: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    if not identity.has_run or not identity.has_session:
        raise ValueError('runtime report requires an authoritative run identity')
    return runtime_paths.quality_dir(repo_root, identity) / change_id / 'runtime-report.json'


# 计算 stop-check-summary 的输出路径。
def stop_summary_path(
    repo_root: Path,
    identity: Any,
    agent: str,
) -> Path:
    """参数：
        repo_root: 当前函数使用的输入参数。
        identity: 当前函数使用的输入参数。
        agent: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    del agent
    if not identity.has_run or not identity.has_session:
        raise ValueError('Stop summary requires an authoritative run identity')
    return runtime_paths.agent_log_dir(repo_root, identity) / 'stop-check-summary.json'


# 写入停止检查摘要文档。
def write_summary(path: Path, payload: dict[str, Any]) -> None:
    """参数：
        path: 当前函数使用的输入参数。
        payload: 当前函数使用的输入参数。

    返回：
        当前函数的计算结果。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
