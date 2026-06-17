"""文件分类器：根据路径将文件归类到预定义类别，确定是否需要 quality gate。

由 post-write hook 调用，为每个被修改的文件打上 category、risk_level、
quality_target 等标签，写入 changed-files.jsonl 作为 stop hook 校验依据。
"""
from __future__ import annotations

from dataclasses import dataclass
import re


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
    ("acceptance-contract", ["docs/acceptance-contracts/**"], True, "acceptance-contracts", "medium", True),
    ("ui-template", ["src/session_browser/web/templates/**/*.html", "src/session_browser/web/templates/*.html"], True, "session-detail", "medium", True),
    ("ui-css", ["src/session_browser/web/static/**/*.css", "src/session_browser/web/static/*.css"], True, "session-detail", "medium", True),
    ("ui-js", ["src/session_browser/web/static/**/*.js", "src/session_browser/web/static/*.js"], True, "session-detail", "medium", True),
    ("python-src", ["src/session_browser/**/*.py", "src/session_browser/*.py"], True, "python-src", "medium", True),
    ("test", ["tests/**/*.py", "tests/*.py", "tests/**/*.js", "tests/*.js", "tests/**/*.ts", "tests/*.ts"], True, "acceptance-contracts", "medium", True),
    ("hook", [".claude/hooks/**", ".codex/hooks/**", ".qoder/hooks/**", "scripts/claude_hooks/**", "scripts/hooks/**", "scripts/agent_hooks/**"], True, "hook-runtime", "high", True),
    ("quality-gate", ["scripts/quality/**"], True, "hook-runtime", "high", True),
    ("harness", ["harness/**", "scripts/harness/**"], True, "harness", "high", True),
    ("openspec", ["openspec/**"], True, "harness", "medium", True),
    ("agent-config", ["AGENTS.md", "CLAUDE.md", "skills/**", ".agents/skills/**", ".claude/settings.json", ".claude/agents/**", ".claude/commands/**", ".claude/skills/**", ".codex/**", ".qoder/**"], True, "hook-runtime", "high", True),
    ("docs", ["README.md", "docs/**"], False, None, "low", True),
    ("local-or-generated", ["tmp/**", "data/**", "output/**", ".venv/**", ".pytest_cache/**", "**/*.sqlite", "**/*.sqlite3", "**/*.db"], False, None, "local", True),
]


# 03. 路径规范化
def normalize_repo_path(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.strip("/")


# 04. glob 匹配：使用正则支持 ** 语义。
def _glob_match(path: str, pattern: str) -> bool:
    """支持 ** 语义的 glob 匹配。** 匹配零或多个目录段。"""
    p = normalize_repo_path(path)
    pat = normalize_repo_path(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', p))


def _match(path: str, pattern: str) -> bool:
    """文件路径 glob 匹配，优先使用 ** 感知的正则实现。"""
    return _glob_match(path, pattern)


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
    assert classify_file("docs/acceptance-contracts/features/DATA_PRESENTERS.md").quality_target == "acceptance-contracts"
    assert classify_file("tests/backend/test_round_signals.py").quality_target == "acceptance-contracts"
    assert classify_file(".claude/settings.json").quality_target == "hook-runtime"
    assert classify_file(".codex/hooks/stop_check.sh").quality_target == "hook-runtime"
    assert classify_file(".qoder/hooks/stop_check.sh").quality_target == "hook-runtime"
    assert classify_file(".codex/config.toml").quality_target == "hook-runtime"
    assert classify_file("skills/authoring/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file(".agents/skills/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file(".codex/skills/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file(".claude/skills/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file("AGENTS.md").quality_target == "hook-runtime"
    assert classify_file("CLAUDE.md").quality_target == "hook-runtime"
    assert classify_file("tmp/agent_logs/session1/x.jsonl").category == "local-or-generated"


if __name__ == "__main__":
    _self_test()
    print("classify self-test PASS")
