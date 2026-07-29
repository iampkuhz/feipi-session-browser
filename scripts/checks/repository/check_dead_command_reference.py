#!/usr/bin/env python3
"""检查活跃维护资料中的仓库脚本引用是否存在且具备公开或诊断资格。

该检查防止文档和 Agent 规则传播失效或非公开命令。唯一入口 ``check(arguments)`` 返回有序
诊断；任一诊断都表示引用不可可靠执行。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

import yaml
from scripts.checks._framework import CheckResult, argument_parser, repository_root

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


def _load_registry(root: Path) -> tuple[frozenset[str], tuple[str, ...]]:
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


def _catalog_diagnostics(root: Path) -> frozenset[str]:
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


def _source_files(root: Path) -> tuple[Path, ...]:
    """返回 CI、Agent、Skill、规则与维护文档的去重稳定集合。"""
    paths = {root / item for item in RULE_FILES}
    for pattern in SCAN_GLOBS:
        paths.update(root.glob(pattern))
    return tuple(sorted(path for path in paths if path.is_file()))


def _scan_references(
    root: Path, paths: tuple[Path, ...] | None = None
) -> tuple[CommandReference, ...]:
    """提取显式调用 Python/Shell 的仓库脚本命令。"""
    references: list[CommandReference] = []
    for path in paths or _source_files(root):
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            references.extend(
                CommandReference(relative, line_number, match.group("target"))
                for match in REFERENCE_PATTERN.finditer(line)
            )
    return tuple(references)


def _reference_status(
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


def _check_repository(root: Path = ROOT) -> tuple[str, ...]:
    """返回所有失效或非公开的可执行命令引用。"""
    public, patterns = _load_registry(root)
    catalog_leaves = _catalog_diagnostics(root)
    errors: list[str] = []
    for reference in _scan_references(root):
        status = _reference_status(root, reference.target, public, patterns, catalog_leaves)
        if status in {"missing", "non-public"}:
            errors.append(
                f"{reference.source}:{reference.line}: {status} executable reference: "
                f"{reference.target}"
            )
    return tuple(errors)


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回全部失效或非公开命令引用。"""
    parser = argument_parser(description='Check active repository command references.')
    parser.add_argument('--root', default=str(ROOT), help='Repository root to inspect')
    args = parser.parse_args(arguments)
    try:
        errors = _check_repository(Path(args.root).resolve())
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return CheckResult.from_errors([f'[dead-command-reference] FAIL: {exc}'])
    return CheckResult.from_errors(f'[dead-command-reference] FAIL: {error}' for error in errors)
