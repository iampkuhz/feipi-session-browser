#!/usr/bin/env python3
"""语言策略 gate：阻断 agent 规则、提示词、规格流程文档中的英文叙述。"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

POLICY_PATTERNS = [
    "AGENTS.md",
    "CLAUDE.md",
    "skills/**/*.md",
    ".agents/skills/**/*.md",
    ".codex/skills/**/*.md",
    ".claude/skills/**/*.md",
    ".codex/agents/*.toml",
    ".codex/config.toml",
    ".codex/model-instructions.md",
    "harness/**/*.md",
    "openspec/changes/**/*.md",
]

ALLOWED_WORDS = {
    "agent", "agents", "api", "bash", "browser", "claude", "cli", "code",
    "codex", "css", "data", "detail", "gate", "git", "github", "gpt",
    "html", "id", "js", "json", "llm", "mcp", "mhtml", "openspec",
    "pytest", "python", "qoder", "session", "shall", "skill", "skills",
    "subagent", "subagents", "toml", "ui", "url", "yaml",
}

CJK_RE = re.compile(r"[\u3400-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")


def _normalize(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.strip("/")


def _glob_match(path: str, pattern: str) -> bool:
    p = _normalize(path)
    pat = _normalize(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r"\*\*", "\x00")
    regex = regex.replace(r"\*", "[^/]*")
    regex = regex.replace(r"\?", ".")
    regex = regex.replace("\x00/", "(?:.+/)?")
    regex = regex.replace("\x00", ".*")
    return bool(re.match(f"^{regex}$", p))


def _is_policy_path(path: str) -> bool:
    p = _normalize(path)
    if "__pycache__/" in p or p.startswith("tmp/"):
        return False
    return any(_glob_match(p, pattern) for pattern in POLICY_PATTERNS)


def _git_changed_files(root: Path) -> list[str]:
    try:
        output = subprocess.check_output(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    files: list[str] = []
    for raw in output.splitlines():
        if not raw.strip():
            continue
        path = raw[3:] if len(raw) > 3 else raw.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(_normalize(path))
    return files


def _parse_changed_files(value: str | None) -> list[str] | None:
    if not value:
        return None
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [_normalize(str(item)) for item in data if str(item).strip()]


def _target_files(root: Path, explicit_changed: str | None) -> list[Path]:
    changed = _parse_changed_files(explicit_changed)
    if changed is None:
        changed = _parse_changed_files(os.environ.get("QUALITY_CHANGED_FILES"))
    if changed is None:
        changed = _git_changed_files(root)

    result: list[Path] = []
    for rel in changed:
        if not _is_policy_path(rel):
            continue
        path = root / rel
        if path.is_file():
            result.append(path)
    return sorted(set(result))


def _strip_noise(text: str) -> str:
    value = re.sub(r"`[^`]+`", " ", text)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[\w./-]+\.(md|py|toml|json|yaml|yml|sh|css|js|html)\b", " ", value, flags=re.I)
    value = re.sub(r"[/~.][\w./-]+", " ", value)
    value = re.sub(r"\b[A-Z_]{2,}\b", " ", value)
    value = re.sub(r"\b[a-zA-Z]+[-_][\w-]+\b", " ", value)
    return value


def _is_scalar_config_line(line: str) -> bool:
    stripped = line.strip()
    if not re.match(r"^[A-Za-z0-9_.-]+\s*=", stripped):
        return False
    key, _, value = stripped.partition("=")
    key = key.strip()
    value = value.strip().strip('"')
    if key in {"description", "developer_instructions"}:
        return False
    return len(value.split()) <= 1


def _line_violates(line: str) -> bool:
    stripped = line.strip()
    if not stripped or CJK_RE.search(stripped):
        return False
    if stripped in {"---", "+++"}:
        return False
    if stripped.startswith("|") and set(stripped) <= {"|", "-", " ", ":"}:
        return False
    if _is_scalar_config_line(stripped):
        return False

    cleaned = _strip_noise(stripped)
    words = [w.lower().strip("'-") for w in WORD_RE.findall(cleaned)]
    meaningful = [w for w in words if w not in ALLOWED_WORDS]
    return len(meaningful) >= 3


def check_file(path: Path) -> list[str]:
    failures: list[str] = []
    in_fence = False
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rel = path.relative_to(REPO_ROOT)
    for index, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _line_violates(line):
            failures.append(f"{rel}:{index}: 英文叙述应改为中文，英文术语请用反引号或混入中文说明：{line.strip()}")
    return failures


def run_check(root: Path, changed_files: str | None = None) -> list[str]:
    failures: list[str] = []
    for path in _target_files(root, changed_files):
        failures.extend(check_file(path))
    return failures


def _self_test() -> None:
    assert _line_violates("Use this skill only for this repository.")
    assert _line_violates('developer_instructions = "Run deterministic validation and report evidence."')
    assert not _line_violates("默认使用简体中文，命令名如 `pytest` 保持英文。")
    assert not _line_violates('model = "gpt-5.4-mini"')
    assert not _line_violates("- Validation: `python3 scripts/quality/run_quality_gate.py --target harness` passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="检查仓库语言策略")
    parser.add_argument("--changed-files", default=None, help="JSON 数组；省略时读取 QUALITY_CHANGED_FILES 或 git status")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("language policy self-test PASS")
        return 0

    failures = run_check(REPO_ROOT, args.changed_files)
    if failures:
        print("language policy gate FAIL")
        for item in failures:
            print(f"[FAIL] {item}")
        return 1
    print("language policy gate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
