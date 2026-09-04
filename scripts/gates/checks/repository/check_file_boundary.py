"""统一检查仓库文件边界。

本文件统一守护仓库文件和公开脚本边界：必需入口必须存在；禁止路径、忽略文件和数据库
不得进入 Git；Gate 根目录必须符合当前阶段布局；维护资料中的脚本命令必须指向 manifest
登记的公开入口。Git 或配置无法可靠读取时直接失败，避免检查异常被误当成通过。唯一公开
入口是 ``check(arguments)``，返回诊断表示仓库边界不符合政策。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml
from scripts.gates.checks.check_protocol import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()
MANIFEST_RELATIVE_PATH = Path('harness/manifest.yaml')
MANIFEST_KEY = 'forbidden_root_paths'
GIT_TIMEOUT_SECONDS = 30

# 仓库运行与维护依赖的稳定入口。重命名入口时必须同步更新这里和对应测试。
REQUIRED_PATHS = (
    'scripts/gates/cli.py',
    'scripts/gates/catalog/gate_contracts.py',
    'scripts/gates/catalog/recipe_dsl.py',
    'scripts/gates/catalog/registry.py',
    'scripts/gates/catalog/validation.py',
    'scripts/gates/planning/change_snapshot.py',
    'scripts/gates/planning/trigger_matcher.py',
    'scripts/gates/planning/plan_compiler.py',
    'scripts/gates/execution/command_adapter.py',
    'scripts/gates/execution/process_supervisor.py',
    'scripts/gates/execution/outcome_classifier.py',
    'scripts/gates/execution/run_orchestrator.py',
    'scripts/gates/evidence/receipt_store.py',
    'scripts/gates/presentation/terminal_ui.py',
    'scripts/gates/maintenance/health_audit.py',
    'scripts/gates/checks/check_protocol.py',
    'scripts/gates/checks/check_registry.py',
    'scripts/gates/checks/repository/check_acceptance_traceability.py',
    'harness/agent-policy.manifest.yaml',
    'harness/skill-registry.yaml',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'harness/README.md',
    'docs/acceptance-cases/README.md',
)
GATE_ROOT = Path('scripts/gates')
ALLOWED_GATE_ROOT_FILES = frozenset({'cli.py'})
ALLOWED_GATE_ROOT_DIRECTORIES = frozenset(
    {
        'catalog',
        'planning',
        'execution',
        'evidence',
        'presentation',
        'maintenance',
        'checks',
    }
)
DATABASE_SUFFIXES = ('.sqlite', '.sqlite3', '.db')
COMMAND_REFERENCE_PATTERN = re.compile(
    r'(?:\b(?:python(?:3)?|bash)\s+|(?<![\w.-])\./)'
    r'(?P<target>scripts/[A-Za-z0-9_./*?{}-]+\.(?:py|sh))'
)
COMMAND_REFERENCE_GLOBS = (
    '.github/**/*',
    '.claude/agents/**/*.md',
    '.claude/commands/**/*.md',
    '.codex/agents/**/*.toml',
    '.qoder/agents/**/*.md',
    'skills/authoring/**/*.md',
    'harness/**/*.md',
    'docs/**/*.md',
)
COMMAND_REFERENCE_FILES = (
    'AGENTS.md',
    'CLAUDE.md',
    '.qoder/AGENTS.md',
    '.codex/model-instructions.md',
    'scripts/README.md',
)


@dataclass(frozen=True)
class _IgnoredTrackedFinding:
    """保存一条被 ignore 规则命中却仍受 Git 追踪的路径。"""

    path: str
    source: str
    line: str
    pattern: str


@dataclass(frozen=True, slots=True)
class CommandReference:
    """保存维护资料中的脚本命令及来源位置。"""

    source: str
    line: int
    target: str


def _manifest(root: Path) -> dict:
    """读取 Harness manifest；公开命令和禁止路径共用这一真源。"""

    data = yaml.safe_load((root / MANIFEST_RELATIVE_PATH).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{MANIFEST_RELATIVE_PATH} must contain a mapping')
    return data


def _public_script_paths(root: Path) -> frozenset[str]:
    """从 manifest 的 public_executables 提取公开 Python/Shell 脚本路径。"""

    commands = _manifest(root).get('public_executables')
    if not isinstance(commands, dict) or not all(
        isinstance(command, str) for command in commands.values()
    ):
        raise ValueError('harness/manifest.yaml public_executables must be a string mapping')
    targets: set[str] = set()
    for command in commands.values():
        match = re.search(r'(?:^|\s)(?:\./)?(scripts/\S+?\.(?:py|sh))(?=\s|$)', command)
        if match:
            targets.add(match.group(1))
    return frozenset(targets)


def _command_reference_sources(root: Path) -> tuple[Path, ...]:
    """返回需要审计公开命令的维护资料集合。"""

    paths = {root / item for item in COMMAND_REFERENCE_FILES}
    for pattern in COMMAND_REFERENCE_GLOBS:
        paths.update(root.glob(pattern))
    return tuple(sorted(path for path in paths if path.is_file()))


def _scan_references(
    root: Path, paths: tuple[Path, ...] | None = None
) -> tuple[CommandReference, ...]:
    """提取显式执行的仓库 Python/Shell 脚本命令。"""

    references: list[CommandReference] = []
    for path in paths or _command_reference_sources(root):
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            references.extend(
                CommandReference(relative, line_number, match.group('target'))
                for match in COMMAND_REFERENCE_PATTERN.finditer(line)
            )
    return tuple(references)


def _reference_status(root: Path, target: str, public: frozenset[str]) -> str:
    """区分脚本命令缺失、内部实现误公开和合法公开入口。"""

    if not (root / target).is_file():
        return 'missing'
    return 'public' if target in public else 'non-public'


def _check_command_references(root: Path) -> tuple[str, ...]:
    """返回维护资料中失效或绕过公开入口的脚本命令。"""

    public = _public_script_paths(root)
    errors: list[str] = []
    for reference in _scan_references(root):
        status = _reference_status(root, reference.target, public)
        if status != 'public':
            errors.append(
                f'{reference.source}:{reference.line}: {status} executable reference: '
                f'{reference.target}'
            )
    return tuple(errors)


def _product_python_paths(root: Path) -> tuple[str, ...]:
    """列出当前仓库边界之外的产品 Python 源码。"""

    source_root = root / 'src' / 'session_browser'
    if not source_root.is_dir():
        return ()
    return tuple(
        path.relative_to(root).as_posix()
        for path in sorted(source_root.rglob('*.py'))
        if '__pycache__' not in path.parts
    )


def _run_git(
    root: Path,
    args: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """执行 Git 命令；启动失败和超时由调用方统一转换为阻断诊断。"""
    return subprocess.run(
        ['git', *args],
        cwd=root,
        input=input_bytes,
        capture_output=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )


def _git_output(root: Path, args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    """读取必须成功的 Git 输出，任何错误都采用 fail-closed。"""
    try:
        result = _run_git(root, args, input_bytes=input_bytes)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail or result.returncode}")
    return result.stdout


def _split_nul_paths(raw: bytes) -> list[str]:
    """解析 NUL 分隔路径，确保空格和特殊字符不会破坏路径边界。"""
    return [item.decode('utf-8', errors='replace') for item in raw.split(b'\0') if item]


def _load_forbidden_paths(manifest_path: Path) -> tuple[str, ...]:
    """只从 manifest 的 ``forbidden_root_paths`` 读取禁止路径真源。"""
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        # 这是仓库必须维护的政策文件；明确缺失属于仓库违规，而不是运行环境故障。
        raise ValueError(f'manifest is missing: {manifest_path}') from exc
    except (OSError, UnicodeError) as exc:
        raise OSError(f'cannot read manifest {manifest_path}: {exc}') from exc
    except yaml.YAMLError as exc:
        raise ValueError(f'cannot read manifest {manifest_path}: {exc}') from exc
    if not isinstance(document, dict):
        raise ValueError(f'manifest must be a mapping: {manifest_path}')
    paths = document.get(MANIFEST_KEY)
    if not isinstance(paths, list) or not paths:
        raise ValueError(f'manifest key {MANIFEST_KEY!r} must be a non-empty list')

    normalized: list[str] = []
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{MANIFEST_KEY} entries must be non-empty strings')
        relative = Path(value)
        if relative.is_absolute() or '..' in relative.parts or relative == Path('.'):
            raise ValueError(f'{MANIFEST_KEY} entry must be repository-relative: {value}')
        normalized.append(relative.as_posix().rstrip('/'))
    if len(normalized) != len(set(normalized)):
        raise ValueError(f'{MANIFEST_KEY} entries must be unique')
    return tuple(normalized)


def _path_exists(path: Path) -> bool:
    """同时识别正常路径和悬空符号链接。"""
    return path.exists() or os.path.lexists(path)


def _candidate_paths(root: Path, all_tracked: bool) -> list[str]:
    """读取本次新增/修改路径或全部追踪路径，并排除正在删除的清理项。"""
    args = (
        ['ls-files', '-z']
        if all_tracked
        else ['diff', '--cached', '--name-only', '-z', '--diff-filter=ACMR']
    )
    paths = _split_nul_paths(_git_output(root, args))
    return [path for path in paths if _path_exists(root / path)]


def _ignored_findings(root: Path, paths: list[str]) -> tuple[_IgnoredTrackedFinding, ...]:
    """找出最终被 ignore 规则命中的路径；否定规则恢复的路径不报错。"""
    if not paths:
        return ()
    payload = ''.join(f'{path}\0' for path in paths).encode()
    try:
        result = _run_git(
            root,
            [
                '-c',
                'core.excludesFile=/dev/null',
                'check-ignore',
                '--no-index',
                '-v',
                '-z',
                '--stdin',
            ],
            input_bytes=payload,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'git check-ignore failed: {exc}') from exc
    if result.returncode == 1:
        return ()
    if result.returncode != 0:
        detail = result.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'git check-ignore failed: {detail or result.returncode}')

    parts = result.stdout.split(b'\0')
    findings: list[_IgnoredTrackedFinding] = []
    for index in range(0, len(parts) - 1, 4):
        if index + 3 >= len(parts):
            break
        source, line, pattern, path = (
            value.decode('utf-8', errors='replace') for value in parts[index : index + 4]
        )
        if not pattern.startswith('!'):
            findings.append(_IgnoredTrackedFinding(path, source, line, pattern))
    return tuple(findings)


def _is_below(path: str, root_path: str) -> bool:
    """判断 Git 路径是否等于或位于某个禁止根路径下。"""
    return path == root_path or path.startswith(f'{root_path}/')


def _gate_root_layout_errors(root: Path) -> list[str]:
    """返回 Gate 根目录中不属于当前阶段布局的源码路径。"""

    gate_root = root / GATE_ROOT
    if not gate_root.is_dir():
        return []
    errors: list[str] = []
    for entry in sorted(gate_root.iterdir(), key=lambda path: path.name):
        if entry.name == '__pycache__':
            continue
        allowed = (
            entry.name in ALLOWED_GATE_ROOT_DIRECTORIES
            if entry.is_dir()
            else entry.name in ALLOWED_GATE_ROOT_FILES
        )
        if not allowed:
            errors.append(f'Gate 根目录路径未登记: {entry.relative_to(root).as_posix()}')
    return errors


def _validate(root: Path, manifest_path: Path, all_tracked: bool) -> list[str]:
    """一次完成公开入口、磁盘路径和 Git 追踪边界检查。"""

    forbidden_paths = _load_forbidden_paths(manifest_path)
    errors = [f'缺少必需路径: {path}' for path in REQUIRED_PATHS if not _path_exists(root / path)]
    errors.extend(_gate_root_layout_errors(root))
    errors.extend(
        f'禁止根路径不应出现在仓库磁盘: {path}'
        for path in forbidden_paths
        if _path_exists(root / path)
    )

    candidates = _candidate_paths(root, all_tracked)
    errors.extend(
        f'{item.path}: 被 ignore 规则追踪 ({item.source}:{item.line}:{item.pattern})'
        for item in _ignored_findings(root, candidates)
    )
    for path in candidates:
        if any(_is_below(path, forbidden) for forbidden in forbidden_paths):
            errors.append(f'禁止根路径不应进入 Git tracked: {path}')
        if path.lower().endswith(DATABASE_SUFFIXES):
            errors.append(f'数据库文件不应进入 Git tracked: {path}')
    errors.extend(f'产品 Python 路径不符合仓库边界: {path}' for path in _product_python_paths(root))
    errors.extend(f'公开命令违规: {error}' for error in _check_command_references(root))
    return errors


def check(arguments: list[str]) -> CheckResult:
    """解析检查范围并返回全部仓库文件政策违规。"""
    parser = argument_parser(description='Validate repository file policy')
    parser.add_argument('--root', default=str(REPO_ROOT), help='Repository root to inspect')
    parser.add_argument('--manifest', help='Manifest path, relative to --root by default')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--staged', action='store_true', help='Check staged changed paths')
    mode.add_argument('--all-tracked', action='store_true', help='Check every tracked path')
    args = parser.parse_args(arguments)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST_RELATIVE_PATH
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        errors = _validate(root, manifest_path, args.all_tracked)
    except RuntimeError as exc:
        return CheckResult.execution_failure(
            [f'repository file policy cannot inspect repository: {exc}'],
            reason='dependency-unavailable',
        )
    except (OSError, UnicodeError) as exc:
        return CheckResult.execution_failure(
            [f'repository file policy cannot read required input: {exc}'],
            reason='input-unavailable',
        )
    except ValueError as exc:
        # Manifest 内容不符合仓库规则是已完成的领域判定，而不是执行环境故障。
        return CheckResult.from_errors([f'repository file policy violation: {exc}'])
    return CheckResult.from_errors(errors)
