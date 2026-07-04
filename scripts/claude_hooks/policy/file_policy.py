"""提供 file policy 脚本能力。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..classify import classify_file
from ..paths import rel_to_repo

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
    """参数：
        path: Candidate 文件路径 reported by 写入 tool。
        repo_root: repo root used到normalize 路径。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    rel = rel_to_repo(path, repo_root)
    cls = classify_file(rel)
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
