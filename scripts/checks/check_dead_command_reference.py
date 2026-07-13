#!/usr/bin/env python3
"""负责检查活跃维护资料中的仓库脚本命令是否仍可执行。

不负责维护公开入口副本；公开命令与诊断命名约定均来自 harness manifest，
Gate leaf 还会从 typed catalog 的实际命令派生；由 repository check 入口调用。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

import yaml
from scripts.checks._framework import repository_root

ROOT = repository_root()

from scripts.gates.catalog import CATALOG  # noqa: E402

MANIFEST_PATH = Path("harness/manifest.yaml")
REFERENCE_PATTERN = re.compile(
    r"(?:\b(?:python(?:3)?|bash)\s+|(?<![\w.-])\./)"
    r"(?P<target>scripts/[A-Za-z0-9_./*?{}-]+\.(?:py|sh))"
)
SCAN_GLOBS = (
    ".github/**/*",
    ".claude/agents/**/*.md",
    ".claude/commands/**/*.md",
    ".codex/agents/**/*.toml",
    ".qoder/agents/**/*.md",
    "skills/authoring/**/*.md",
    "harness/**/*.md",
    "docs/**/*.md",
)
RULE_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".qoder/AGENTS.md",
    ".codex/model-instructions.md",
    "scripts/README.md",
)
WILDCARD_MARKERS = frozenset("*?{}[]")


@dataclass(frozen=True, slots=True)
class CommandReference:
    """保存命令目标及其稳定来源位置。"""

    source: str
    line: int
    target: str


def _manifest(root: Path) -> dict:
    """读取唯一公开可执行 registry。"""
    data = yaml.safe_load((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{MANIFEST_PATH} must contain a mapping")
    return data


def _command_target(command: str) -> str | None:
    """从 manifest 命令值中提取仓库脚本目标。"""
    match = re.search(r"(?:^|\s)(?:\./)?(scripts/\S+?\.(?:py|sh))(?=\s|$)", command)
    return match.group(1) if match else None


def load_registry(root: Path) -> tuple[frozenset[str], tuple[str, ...]]:
    """从 manifest 派生公开精确路径与诊断 pattern。"""
    data = _manifest(root)
    commands = data.get("public_executables")
    patterns = data.get("diagnostic_executables")
    if not isinstance(commands, dict) or not all(
        isinstance(item, str) for item in commands.values()
    ):
        raise ValueError("harness/manifest.yaml public_executables must be a string mapping")
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise ValueError("harness/manifest.yaml diagnostic_executables must be a string list")
    public = frozenset(
        target for command in commands.values() if (target := _command_target(command)) is not None
    )
    return public, tuple(patterns)


def catalog_diagnostics(root: Path) -> frozenset[str]:
    """从 typed catalog 的命令声明派生精确 diagnostic leaf。"""
    result: set[str] = set()
    for gate in CATALOG.gates:
        if gate.command is None:
            continue
        arguments = [*gate.command.argv, *gate.command.existing_args]
        arguments.extend(
            argument for command in gate.command.target_argv for argument in command.argv
        )
        arguments.extend(
            argument for optional in gate.command.optional_args for argument in optional.argv
        )
        for argument in arguments:
            candidate = argument.removeprefix("{repo_root}/")
            if candidate.startswith("scripts/checks/") and Path(candidate).suffix in {".py", ".sh"}:
                result.add(candidate)
    return frozenset(result)


def source_files(root: Path) -> tuple[Path, ...]:
    """返回 CI、Agent、Skill、规则与维护文档的去重稳定集合。"""
    paths = {root / item for item in RULE_FILES}
    for pattern in SCAN_GLOBS:
        paths.update(root.glob(pattern))
    return tuple(sorted(path for path in paths if path.is_file()))


def scan_references(
    root: Path, paths: tuple[Path, ...] | None = None
) -> tuple[CommandReference, ...]:
    """提取显式调用 Python/Shell 的仓库脚本命令。"""
    references: list[CommandReference] = []
    for path in paths or source_files(root):
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            references.extend(
                CommandReference(relative, line_number, match.group("target"))
                for match in REFERENCE_PATTERN.finditer(line)
            )
    return tuple(references)


def reference_status(
    root: Path,
    target: str,
    public: frozenset[str],
    diagnostic_patterns: tuple[str, ...],
    catalog_leaves: frozenset[str],
) -> str:
    """按存在性、公开 registry 与诊断资格返回稳定分类。"""
    if any(marker in target for marker in WILDCARD_MARKERS) or not (root / target).is_file():
        return "missing"
    if target in public:
        return "public"
    if target in catalog_leaves or any(
        fnmatchcase(target, pattern) for pattern in diagnostic_patterns
    ):
        return "diagnostic"
    return "non-public"


def check_repository(root: Path = ROOT) -> tuple[str, ...]:
    """返回所有失效或非公开的可执行命令引用。"""
    public, patterns = load_registry(root)
    catalog_leaves = catalog_diagnostics(root)
    errors: list[str] = []
    for reference in scan_references(root):
        status = reference_status(root, reference.target, public, patterns, catalog_leaves)
        if status in {"missing", "non-public"}:
            errors.append(
                f"{reference.source}:{reference.line}: {status} executable reference: "
                f"{reference.target}"
            )
    return tuple(errors)


def main() -> int:
    """执行检查并返回适合 CI 的退出码。"""
    try:
        errors = check_repository()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[dead-command-reference] FAIL: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"[dead-command-reference] FAIL: {error}", file=sys.stderr)
        return 1
    return 0
