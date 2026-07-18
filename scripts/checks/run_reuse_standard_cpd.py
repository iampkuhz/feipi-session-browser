#!/usr/bin/env python3
"""运行 PMD CPD 标准复用门禁，默认仅检查变更 Java 文件。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_runtime.events import evidence as changed_file_utils  # noqa: E402

DEFAULT_MODE = 'incremental'
VALID_MODES = {'incremental', 'full'}
SUMMARY_RELATIVE_PATH = Path(
    '.local/gradle/root-build/reports/reuse-analysis/standard-cpd-summary.json'
)
FILE_LIST_RELATIVE_PATH = Path(
    '.local/gradle/root-build/tmp/reuse-standard-cpd/reuse-cpd-file-list.txt'
)


class CpdInputBlocked(RuntimeError):  # noqa: N818
    """表示默认增量 CPD 缺少安全输入，不能自动降级为全量。"""


# 判断生产 Java 源码路径。
def is_production_java_path(path: str) -> bool:
    """参数：
        path: 仓库相对路径。

    返回：
        如果路径指向生产 Java 源文件则返回 true。
    """
    rel = changed_file_utils.normalize_path(path)
    return rel.startswith('java/') and '/src/main/java/' in rel and rel.endswith('.java')


# 判断 CPD 策略路径。
def is_reuse_policy_path(path: str) -> bool:
    """参数：
        path: 仓库相对路径。

    返回：
        如果路径指向复用检测策略则返回 true。
    """
    return changed_file_utils.normalize_path(path).startswith('config/reuse-policy/')


# 解析 changed-files JSON。
def parse_changed_files(value: str | None) -> list[str]:
    """参数：
        value: 变更文件 JSON 数组字符串。

    返回：
        去重后的变更文件列表。
    """
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CpdInputBlocked(f'changed-files JSON 解析失败: {exc}') from exc
    if not isinstance(parsed, list):
        raise CpdInputBlocked('changed-files 必须是 JSON string array')
    invalid = [item for item in parsed if not isinstance(item, str)]
    if invalid:
        raise CpdInputBlocked('changed-files 必须只包含 string 路径')
    return changed_file_utils.dedupe_paths(parsed)


# 解析默认 mode。
def normalize_mode(value: str | None) -> str:
    """参数：
        value: 命令行或环境变量中的模式。

    返回：
        规范化后的模式。
    """
    mode = (value or DEFAULT_MODE).strip().lower()
    if mode not in VALID_MODES:
        raise CpdInputBlocked(f'unknown CPD mode: {value!r}')
    return mode


# 收集 changed-files 证据。
def resolve_changed_files(repo_root: Path, explicit: str | None) -> tuple[list[str], str]:
    """参数：
        repo_root: 仓库根目录。
        explicit: 命令行显式传入的变更文件 JSON，或 auto。

    返回：
        变更文件列表与来源标签。
    """
    if explicit and explicit != 'auto':
        return parse_changed_files(explicit), 'cli'

    env_value = os.environ.get('QUALITY_CHANGED_FILES')
    if env_value:
        return parse_changed_files(env_value), 'QUALITY_CHANGED_FILES'

    dirty = changed_file_utils.read_git_dirty_files(repo_root)
    return dirty, 'git-dirty'


# 选择增量 CPD 输入。
def select_incremental_java_files(repo_root: Path, changed_files: list[str]) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        changed_files: 候选变更文件列表。

    返回：
        存在的生产 Java 变更文件，保持仓库相对路径。
    """
    selected: list[str] = []
    for rel in changed_file_utils.dedupe_paths(changed_files):
        if not is_production_java_path(rel):
            continue
        if (repo_root / rel).is_file():
            selected.append(rel)
    return selected


# 写入复制粘贴检测文件清单。
def write_cpd_file_list(repo_root: Path, files: list[str], file_list: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。
        files: 仓库相对输入文件列表。
        file_list: 要写入的清单文件路径。

    返回：
        已写入的清单文件路径。
    """
    file_list.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        (repo_root / rel).resolve().as_posix() for rel in changed_file_utils.dedupe_paths(files)
    ]
    file_list.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    return file_list


# 写入审计摘要。
def write_summary(
    repo_root: Path,
    *,
    status: str,
    mode: str,
    changed_files: list[str],
    cpd_input_files: list[str],
    changed_files_source: str,
    reason: str = '',
    summary_path: Path | None = None,
) -> Path:
    """参数：
        repo_root: 仓库根目录。
        status: 门禁状态。
        mode: 运行模式。
        changed_files: 原始变更文件列表。
        cpd_input_files: 实际检测输入文件列表。
        changed_files_source: 变更文件来源标签。
        reason: 审计原因说明。
        summary_path: 可选摘要输出路径。

    返回：
        已写入的摘要路径。
    """
    path = summary_path or repo_root / SUMMARY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'engine': 'PMD_CPD_CLI',
        'status': status,
        'mode': mode,
        'inputMechanism': 'pmd-cpd --file-list',
        'changedFilesSource': changed_files_source,
        'changedFileCount': len(changed_file_utils.dedupe_paths(changed_files)),
        'cpdInputFiles': changed_file_utils.dedupe_paths(cpd_input_files),
        'cpdInputCount': len(changed_file_utils.dedupe_paths(cpd_input_files)),
        'fullScan': mode == 'full',
        'dirScanUsed': False,
        'reason': reason,
    }
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    return path


# 构建 Gradle 命令。
def build_gradle_command(repo_root: Path, mode: str, file_list: Path | None) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        mode: 运行模式。
        file_list: 增量模式使用的文件清单。

    返回：
        Gradle 命令参数列表。
    """
    gradlew = repo_root / 'gradlew'
    command = [str(gradlew), 'reuseStandardCpd', f'-PfeipiReuseCpdMode={mode}', '--console=plain']
    if mode == 'incremental':
        if file_list is None:
            raise CpdInputBlocked('incremental CPD requires a PMD file-list')
        command.insert(2, f'-PfeipiReuseCpdFileList={file_list.resolve().as_posix()}')
    return command


# 运行 Gradle。
def run_gradle(command: list[str], repo_root: Path) -> int:
    """参数：
        command: 待执行命令。
        repo_root: 仓库根目录。

    返回：
        子进程退出码。
    """
    proc = subprocess.run(command, cwd=repo_root, check=False)
    return proc.returncode


# 执行默认增量路径。
def run_incremental(repo_root: Path, changed_files_arg: str | None) -> int:
    """参数：
        repo_root: 仓库根目录。
        changed_files_arg: 命令行变更文件参数。

    返回：
        进程退出码。
    """
    changed_files, source = resolve_changed_files(repo_root, changed_files_arg)
    if any(is_reuse_policy_path(path) for path in changed_files):
        write_summary(
            repo_root,
            status='BLOCKED',
            mode='incremental',
            changed_files=changed_files,
            cpd_input_files=[],
            changed_files_source=source,
            reason='CPD policy changed; run explicit --mode full to refresh the baseline.',
        )
        print(
            '[reuseStandardCpd] BLOCKED: CPD policy changed; '
            'default incremental mode will not silently run a full scan. Use --mode full.',
            file=sys.stderr,
        )
        return 2

    java_files = select_incremental_java_files(repo_root, changed_files)
    if not java_files:
        summary = write_summary(
            repo_root,
            status='PASS',
            mode='incremental',
            changed_files=changed_files,
            cpd_input_files=[],
            changed_files_source=source,
            reason='No changed production Java files; full CPD was not invoked.',
        )
        print(f'[reuseStandardCpd] PASS: no changed production Java files; summary={summary}')
        return 0

    file_list = write_cpd_file_list(repo_root, java_files, repo_root / FILE_LIST_RELATIVE_PATH)
    print(
        f'[reuseStandardCpd] incremental CPD input count={len(java_files)} '
        f'file-list={file_list.relative_to(repo_root)}',
        file=sys.stderr,
    )
    command = build_gradle_command(repo_root, 'incremental', file_list)
    return run_gradle(command, repo_root)


# 执行显式 full 路径。
def run_full(repo_root: Path) -> int:
    """参数：
        repo_root: 仓库根目录。

    返回：
        进程退出码。
    """
    print('[reuseStandardCpd] full CPD explicitly requested', file=sys.stderr)
    command = build_gradle_command(repo_root, 'full', None)
    return run_gradle(command, repo_root)


# 构造命令行解析器。
def build_parser() -> argparse.ArgumentParser:
    """返回：
    命令行解析器。
    """
    parser = argparse.ArgumentParser(description='Run reuseStandardCpd with incremental defaults.')
    parser.add_argument(
        '--mode',
        default=os.environ.get('FEIPI_REUSE_CPD_MODE')
        or os.environ.get('QUALITY_REUSE_CPD_MODE')
        or DEFAULT_MODE,
        choices=sorted(VALID_MODES),
        help='CPD mode. Default: incremental.',
    )
    parser.add_argument(
        '--changed-files',
        default='auto',
        help="JSON array of changed paths, or 'auto' to read QUALITY_CHANGED_FILES/git dirty.",
    )
    parser.add_argument('--repo-root', default=str(REPO_ROOT), help='Repository root.')
    return parser


# 脚本入口。
def main(argv: list[str] | None = None) -> int:
    """参数：
        argv: 可选命令行参数。

    返回：
        进程退出码。
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    try:
        mode = normalize_mode(args.mode)
        if mode == 'full':
            return run_full(repo_root)
        return run_incremental(repo_root, args.changed_files)
    except CpdInputBlocked as exc:
        print(f'[reuseStandardCpd] BLOCKED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
