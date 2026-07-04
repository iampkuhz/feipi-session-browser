"""收集 agent 与 quality gate 共享的 changed-files evidence。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.claude_hooks import paths as runtime_paths

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_LOG_DIR = runtime_paths.agent_log_dir(REPO_ROOT)
DEFAULT_CHANGED_FILES = AGENT_LOG_DIR / 'changed-files.jsonl'
DEFAULT_SESSION_ID_FILE = AGENT_LOG_DIR / 'session-id.txt'
DEFAULT_BASE_COMMIT_FILE = AGENT_LOG_DIR / 'base-commit.txt'

GIT_STATUS_PATH_OFFSET = 3
GIT_STATUS_MIN_LINE_LENGTH = GIT_STATUS_PATH_OFFSET + 1


# 规范化路径。
def normalize_path(path: str) -> str:
    """参数：
        path: 待检查的路径。

    返回：
        normalize 路径 字符串。
    """
    value = path.replace('\\', '/').strip()
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 维护dedupe 路径。
def dedupe_paths(paths: list[str]) -> list[str]:
    """参数：
        paths: 待检查的路径列表。

    返回：
        结果列表。
    """
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        normalized = normalize_path(path)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# 读取session id。
def read_session_id(session_id_file: Path = DEFAULT_SESSION_ID_FILE) -> str | None:
    """参数：
        session_id_file: session id file 参数。

    返回：
        read session id 字符串。
    """
    if not session_id_file.exists():
        return None
    value = session_id_file.read_text(encoding='utf-8').strip()
    return value or None


# 读取recorded changed-files 文件。
def read_recorded_changed_files(
    session_id: str | None = None,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    agent_id: str | None = None,
) -> list[str]:
    """参数：
        session_id: 可选session id used到filter hook record。
        changed_files_path: 路径到 changed-文件 JSONL 文件。
        agent_id: 可选agent id used到filter record到a specific agent。

    返回：
        结果列表。
    """
    if not changed_files_path.exists():
        return []

    files: list[str] = []
    for raw_line in changed_files_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if session_id and record.get('sessionId') != session_id:
            continue
        if agent_id:
            record_agent_id = record.get('agentId') or ''
            if record_agent_id != agent_id:
                continue
        file_path = record.get('file') or record.get('file_path')
        if isinstance(file_path, str) and file_path:
            files.append(file_path)
    return dedupe_paths(files)


# 读取recorded changed-files 文件 路径。
def read_recorded_changed_files_from_paths(
    changed_files_paths: list[Path],
    session_id: str | None = None,
    agent_id: str | None = None,
) -> list[str]:
    """参数：
        changed_files_paths: 待检查的路径列表。
        session_id: 用于筛选记录的 session id。
        agent_id: 用于筛选记录的 agent id。

    返回：
        结果列表。
    """
    files: list[str] = []
    for path in changed_files_paths:
        files.extend(read_recorded_changed_files(session_id, path, agent_id=agent_id))
    return dedupe_paths(files)


# 解析Git 状态 路径。
def parse_git_status_paths(output: str) -> list[str]:
    """参数：
        output: output 参数。

    返回：
        结果列表。
    """
    files: list[str] = []
    for line in output.splitlines():
        if not line.strip() or len(line) < GIT_STATUS_MIN_LINE_LENGTH:
            continue
        path_text = line[GIT_STATUS_PATH_OFFSET:].strip()
        if not path_text:
            continue
        if ' -> ' in path_text:
            files.extend(part.strip().strip('"') for part in path_text.split(' -> ', 1))
        else:
            files.append(path_text.strip('"'))
    return dedupe_paths(files)


# 读取Git dirty 文件。
def read_git_dirty_files(repo_root: Path = REPO_ROOT) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    try:
        proc = subprocess.run(
            ['git', 'status', '--short', '--untracked-files=all'],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    return parse_git_status_paths(proc.stdout or '')


# 读取base commit。
def read_base_commit(base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE) -> str | None:
    """参数：
        base_commit_file: base commit sentinel 文件路径。

    返回：
        读取到的 base commit 字符串。
    """
    if not base_commit_file.exists():
        return None
    value = base_commit_file.read_text(encoding='utf-8').strip()
    return value or None


# 读取当前 head。
def read_current_head(repo_root: Path = REPO_ROOT) -> str | None:
    """参数：
        repo_root: 仓库根目录。

    返回：
        读取到的当前 HEAD 字符串。
    """
    try:
        proc = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or '').strip()
    return value or None


# 写入base commit missing。
def write_base_commit_if_missing(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
    *,
    overwrite: bool = False,
) -> str | None:
    """参数：
        repo_root: 仓库根目录。
        base_commit_file: base commit sentinel 文件路径。
        overwrite: overwrite 参数。

    返回：
        缺失时写入的 base commit 字符串。
    """
    existing = read_base_commit(base_commit_file)
    if existing and not overwrite:
        return existing

    head = read_current_head(repo_root)
    if not head:
        return None
    try:
        base_commit_file.parent.mkdir(parents=True, exist_ok=True)
        base_commit_file.write_text(head + '\n', encoding='utf-8')
    except OSError:
        return None
    return head


# 读取文件 since base commit。
def read_files_since_base_commit(
    repo_root: Path = REPO_ROOT,
    base_commit_file: Path = DEFAULT_BASE_COMMIT_FILE,
) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        base_commit_file: base commit sentinel 文件路径。

    返回：
        结果列表。

    说明：
        不 仅 ``base.HEAD``. This fail-closed behavior is 必需 so Bash。
    """
    base_commit = read_base_commit(base_commit_file)
    if not base_commit:
        return []
    paths: list[str] = []
    try:
        proc = subprocess.run(
            ['git', 'diff', '--name-only', '--diff-filter=ACMRD', base_commit],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode == 0:
        paths.extend(line for line in (proc.stdout or '').splitlines() if line.strip())

    try:
        untracked = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        untracked = None
    if untracked is not None and untracked.returncode == 0:
        paths.extend(line for line in (untracked.stdout or '').splitlines() if line.strip())

    return dedupe_paths(paths)


# 收集当前 session/agent 需要纳入 stop gate 的 changed files。
def collect_changed_files(
    session_id: str | None = None,
    *,
    include_git: bool = True,
    repo_root: Path = REPO_ROOT,
    changed_files_path: Path = DEFAULT_CHANGED_FILES,
    base_commit_file: Path | None = None,
    agent_id: str | None = None,
) -> list[str]:
    """参数：
        session_id: 可选session id used到filter hook record。
        include_git: include git 参数。
        repo_root: repo root用于git 命令。
        changed_files_path: 路径到 changed-文件 JSONL 文件。
        base_commit_file: base commit sentinel 文件路径。
        agent_id: 可选agent id到filter hook record到a specific agent。

    返回：
        结果列表。

    说明：
        commit sentinel exists, arbitrary pre-现有 dirty 文件 are 不 routed。
    """
    explicit_base_commit_file = base_commit_file is not None
    if base_commit_file is None:
        base_commit_file = changed_files_path.with_name(DEFAULT_BASE_COMMIT_FILE.name)
    paths = read_recorded_changed_files(session_id, changed_files_path, agent_id=agent_id)
    if include_git or explicit_base_commit_file:
        paths.extend(read_files_since_base_commit(repo_root, base_commit_file))
    return dedupe_paths(paths)


# 解析changed-files 文件 JSON。
def parse_changed_files_json(value: str | None) -> list[str]:
    """参数：
        value: value 参数。

    返回：
        结果列表。
    """
    if value is None:
        return []
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return dedupe_paths([item for item in parsed if isinstance(item, str)])
