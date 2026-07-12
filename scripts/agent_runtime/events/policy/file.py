"""判定写入路径分类、敏感目录阻断与 fail-closed payload 条件。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.paths import rel_to_repo
from scripts.agent_runtime.policy import is_protected_path
from scripts.gates.planner import classify_path

if TYPE_CHECKING:
    from pathlib import Path


# 01. 文件策略结果
@dataclass
class FilePolicyDecision:
    """表示 FilePolicyDecision 的策略判定结果。

    属性：
        allowed: 是否允许继续执行。
        status: 状态值。
        reason: 阻断或放行原因。
        warnings: 警告列表。
        category: 文件分类。
        requires_quality_gate: 该路径是否触发 quality gate evidence。
        quality_target: 需要运行的 quality target。
    """

    allowed: bool
    status: str
    reason: str = ''
    warnings: list[str] = field(default_factory=list)
    category: str = 'unknown'
    requires_quality_gate: bool = False
    quality_target: str | None = None


# 维护评估 write 路径。
def evaluate_write_path(path: str, repo_root: str | Path) -> FilePolicyDecision:
    """维护评估 write 路径。"""
    rel = rel_to_repo(path, repo_root)
    cls = classify_path(rel)
    warnings: list[str] = []

    # 仓库外敏感目录直接阻止。
    raw = str(path)
    if raw.startswith('~/.ssh') or raw.startswith('~/.aws') or '/.ssh/' in raw or '/.aws/' in raw:
        return FilePolicyDecision(
            False, 'BLOCK', '禁止写入 SSH/AWS 敏感目录。', category=cls.category
        )

    # 运行态和生成物允许本地存在, 但需要警告不要纳入 git。
    if cls.category == 'local-or-generated':
        warnings.append(
            '这是本地运行态或生成物路径; 允许写入, 但 Stop/doctor 会阻止进入 git tracked/staged。'
        )

    return FilePolicyDecision(
        allowed=True,
        status='PASS',
        warnings=warnings,
        category=cls.category,
        requires_quality_gate=cls.requires_quality_gate,
        quality_target=cls.quality_target,
    )


WRITE_TOOL_NAMES = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}


def pre_write_payload_block_reason(ctx: Any, repo_root: str | Path) -> str:
    """执行 `pre_write_payload_block_reason` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
    if getattr(ctx, 'parse_error', None):
        return f'pre-write hook payload JSON 解析失败；fail-closed: {ctx.parse_error}'
    tool_name = getattr(ctx, 'tool_name', '')
    candidate_paths = list(getattr(ctx, 'candidate_paths', []))
    if not candidate_paths and (tool_name in WRITE_TOOL_NAMES or not tool_name):
        return '写入类 hook payload 缺少 candidate path；fail-closed。'
    if not getattr(ctx, 'session_id', ''):
        for path in candidate_paths:
            if is_protected_path(path, repo_root):
                return 'protected write 缺少 session id；fail-closed，避免写入共享 evidence。'
    return ''


# 运行脚本自测试场景。
def _self_test() -> None:
    d = evaluate_write_path('src/session_browser/web/static/app.css', '.')
    assert d.allowed
    assert d.requires_quality_gate
    assert d.quality_target == 'session-detail'
    local = evaluate_write_path('tmp/agent_logs/session1/a.jsonl', '.')
    assert local.allowed
    assert local.warnings


if __name__ == '__main__':
    _self_test()
    print('file_policy self-test PASS')
