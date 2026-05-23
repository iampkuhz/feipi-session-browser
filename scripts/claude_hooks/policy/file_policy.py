from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..classify import classify_file
from ..paths import rel_to_repo


# 01. 文件策略结果
@dataclass
class FilePolicyDecision:
    allowed: bool
    status: str
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    category: str = "unknown"
    requires_quality_gate: bool = False
    quality_target: str | None = None


# 02. 写入策略：默认允许，少数明显敏感路径阻止。
def evaluate_write_path(path: str, repo_root: str | Path) -> FilePolicyDecision:
    rel = rel_to_repo(path, repo_root)
    cls = classify_file(rel)
    warnings: list[str] = []

    # 仓库外敏感目录直接阻止。
    raw = str(path)
    if raw.startswith("~/.ssh") or raw.startswith("~/.aws") or "/.ssh/" in raw or "/.aws/" in raw:
        return FilePolicyDecision(False, "BLOCK", "禁止写入 SSH/AWS 敏感目录。", category=cls.category)

    # 运行态和生成物允许本地存在，但需要警告不要纳入 git。
    if cls.category == "local-or-generated":
        warnings.append("这是本地运行态或生成物路径；允许写入，但 Stop/doctor 会阻止进入 git tracked/staged。")

    return FilePolicyDecision(
        allowed=True,
        status="PASS",
        warnings=warnings,
        category=cls.category,
        requires_quality_gate=cls.requires_quality_gate,
        quality_target=cls.quality_target,
    )


# 03. 自测试
def _self_test() -> None:
    d = evaluate_write_path("src/session_browser/web/static/app.css", ".")
    assert d.allowed
    assert d.requires_quality_gate
    assert d.quality_target == "session-detail"
    local = evaluate_write_path("tmp/agent_logs/session1/a.jsonl", ".")
    assert local.allowed
    assert local.warnings


if __name__ == "__main__":
    _self_test()
    print("file_policy self-test PASS")
