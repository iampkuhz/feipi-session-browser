from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import fnmatch


# 01. 分类结果模型
@dataclass(frozen=True)
class FileClassification:
    file: str
    category: str
    requires_quality_gate: bool
    quality_target: str | None
    risk_level: str
    allowed_by_default: bool


# 02. 分类规则
RULES: list[tuple[str, list[str], bool, str | None, str, bool]] = [
    ("ui-template", ["src/session_browser/web/templates/**/*.html", "src/session_browser/web/templates/*.html"], True, "session-detail", "medium", True),
    ("ui-css", ["src/session_browser/web/static/**/*.css", "src/session_browser/web/static/*.css"], True, "session-detail", "medium", True),
    ("ui-js", ["src/session_browser/web/static/**/*.js", "src/session_browser/web/static/*.js"], True, "session-detail", "medium", True),
    ("python-src", ["src/session_browser/**/*.py", "src/session_browser/*.py"], True, "python-src", "medium", True),
    ("test", ["tests/**/*.py", "tests/*.py"], False, None, "low", True),
    ("hook", [".claude/hooks/**", "scripts/claude_hooks/**", "scripts/hooks/**", "scripts/agent_hooks/**"], True, "hook-runtime", "high", True),
    ("quality-gate", ["scripts/quality/**"], True, "hook-runtime", "high", True),
    ("harness", ["harness/**", "scripts/harness/**"], True, "harness", "high", True),
    ("openspec", ["openspec/**"], True, "harness", "medium", True),
    ("claude-config", [".claude/settings.json", ".claude/agents/**", ".claude/commands/**", ".claude/skills/**"], True, "hook-runtime", "high", True),
    ("docs", ["README.md", "AGENTS.md", "CLAUDE.md", "docs/**"], False, None, "low", True),
    ("local-or-generated", ["tmp/**", "data/**", "output/**", ".venv/**", ".pytest_cache/**", "**/*.sqlite", "**/*.sqlite3", "**/*.db"], False, None, "local", True),
]


# 03. 路径规范化
def normalize_repo_path(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.strip("/")


# 04. glob 匹配
def _match(path: str, pattern: str) -> bool:
    p = normalize_repo_path(path)
    pat = normalize_repo_path(pattern)
    if fnmatch.fnmatch(p, pat):
        return True
    # pathlib 的 match 对 ** 语义更接近路径匹配。
    try:
        return PurePosixPath(p).match(pat)
    except Exception:
        return False


# 05. 单文件分类
def classify_file(path: str) -> FileClassification:
    p = normalize_repo_path(path)
    for category, patterns, req, target, risk, allow in RULES:
        if any(_match(p, pattern) for pattern in patterns):
            return FileClassification(
                file=p,
                category=category,
                requires_quality_gate=req,
                quality_target=target,
                risk_level=risk,
                allowed_by_default=allow,
            )
    return FileClassification(
        file=p,
        category="unknown",
        requires_quality_gate=False,
        quality_target=None,
        risk_level="low",
        allowed_by_default=True,
    )


# 06. 多文件目标汇总
def required_quality_targets(files: list[str]) -> list[str]:
    targets: list[str] = []
    for f in files:
        c = classify_file(f)
        if c.requires_quality_gate and c.quality_target and c.quality_target not in targets:
            targets.append(c.quality_target)
    return targets


# 07. 自测试
def _self_test() -> None:
    assert classify_file("src/session_browser/web/templates/session_detail.html").category == "ui-template"
    assert classify_file("src/session_browser/web/static/app.css").category == "ui-css"
    assert classify_file("src/session_browser/foo.py").quality_target == "python-src"
    assert classify_file(".claude/settings.json").quality_target == "hook-runtime"
    assert classify_file("tmp/agent_log/x.jsonl").category == "local-or-generated"


if __name__ == "__main__":
    _self_test()
    print("classify self-test PASS")
