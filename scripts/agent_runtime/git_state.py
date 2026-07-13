"""负责统一执行 Git 查询与采集内容敏感快照；不负责解释 Stop 结果或修改仓库；由 Session、Hook 与 Stop pipeline 调用。"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any


def run(
    repo: Path,
    *args: str,
    check: bool = True,
    text: bool = True,
    timeout: float = 30,
) -> subprocess.CompletedProcess:
    """在指定 checkout 执行 Git；所有 Runtime 调用方共享相同超时与捕获策略。"""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=text,
        timeout=timeout,
    )


def optional(repo: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess | None:
    """执行可选 Git 查询，异常或非零状态统一返回 ``None``。"""
    try:
        result = run(repo, *args, check=False, text=text)
    except (OSError, subprocess.SubprocessError):
        return None
    return result if result.returncode == 0 else None


def output(repo: Path, *args: str) -> str:
    """执行可选 Git 查询并返回去除尾部空白的文本；非零退出码由调用者决定是否容忍。"""
    return run(repo, *args).stdout.strip()


def lines(repo: Path, *args: str) -> list[str]:
    """执行可选 Git 查询并过滤空行，供 Stop 与 Session 身份采集复用。"""
    result = optional(repo, *args)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()] if result else []


def optional_value(repo: Path, *args: str) -> str | None:
    """读取可缺失的单值 Git 事实；查询失败或空结果时返回空值而非伪造证据。"""
    result = optional(repo, *args)
    value = result.stdout.strip() if result else ""
    return value or None


def diff_paths(repo: Path, before: str, after: str) -> list[str]:
    """返回指定 diff 范围的去重路径，保留 Git 对重命名与索引的原始判定。"""
    result = optional(repo, "diff", "--name-only", "--diff-filter=ACMRD", before, after)
    return sorted(dict.fromkeys(result.stdout.splitlines())) if result else []


def repo_root(path: Path) -> Path:
    """解析并严格返回 checkout 顶层目录；无法证明仓库身份时抛出 GitStateError。"""
    result = optional(path, "rev-parse", "--show-toplevel")
    if result is None:
        raise RuntimeError(f"not a Git checkout: {path}")
    return Path(result.stdout.strip()).resolve()


def common_dir(repo: Path) -> Path:
    """解析当前 checkout 的 Git common-dir，并将相对结果绑定到 checkout 根。"""
    raw = output(repo, "rev-parse", "--git-common-dir")
    path = Path(raw)
    return (repo / path).resolve() if not path.is_absolute() else path.resolve()


def head(repo: Path) -> str:
    """读取当前 HEAD 提交；缺失或多值时关闭失败。"""
    return output(repo, "rev-parse", "HEAD")


def branch(repo: Path) -> str:
    """读取当前分支名称；detached HEAD 明确返回空字符串。"""
    return output(repo, "branch", "--show-current")


def parse_status_paths(output: str) -> list[str]:
    """解析 ``git status --short``，rename 同时归因旧、新路径。"""
    files: list[str] = []
    for line in output.splitlines():
        path = line[3:].strip() if len(line) >= 4 else ''
        if ' -> ' in path:
            files.extend(part.strip().strip('"') for part in path.split(' -> ', 1))
        elif path:
            files.append(path.strip('"'))
    return sorted(dict.fromkeys(files))


def dirty_files(repo: Path) -> list[str]:
    """合并工作区、索引与未跟踪路径，供写归因和 Stop 验证使用。"""
    result = optional(repo, 'status', '--short', '--untracked-files=all')
    return parse_status_paths(result.stdout) if result else []


# 内容敏感快照：所有组件必须在同一 checkout 上成功读取，否则关闭失败。
class GitStateError(RuntimeError):
    """无法可靠收集必需 Git 事实时抛出，禁止用猜测继续。"""


def required_query(repo_root: Path, *args: str, text: bool = True):
    """执行必需 Git 查询；任何启动或非零状态都关闭失败。"""
    try:
        proc = run(repo_root, *args, check=False, text=text)
    except Exception as exc:
        raise GitStateError(f'Git query could not start: {" ".join(args)}: {exc}') from exc
    if proc.returncode != 0:
        detail = proc.stderr
        if isinstance(detail, bytes):
            detail = detail.decode(errors='replace')
        detail = detail.strip() or f'exit {proc.returncode}'
        raise GitStateError(f'Git query failed: {" ".join(args)}: {detail}')
    return proc


def required_lines(repo_root: Path, *args: str) -> list[str]:
    """返回必需查询的非空文本行。"""
    proc = required_query(repo_root, *args)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def required_value(repo_root: Path, *args: str) -> str:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    values = required_lines(repo_root, *args)
    if len(values) != 1:
        raise GitStateError(f'Git query did not return one value: {" ".join(args)}')
    return values[0]


def required_bytes(repo_root: Path, *args: str) -> bytes:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    return required_query(repo_root, *args, text=False).stdout


def optional_value_or_empty(repo_root: Path, *args: str) -> str:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    values = lines(repo_root, *args)
    return values[0] if values else ''


def hash_untracked_contents(repo_root: Path, raw_paths: bytes) -> tuple[str, int]:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    digest = hashlib.sha256()
    digest.update(b'feipi-untracked-snapshot-v1\0')
    count = 0
    if not raw_paths:
        return digest.hexdigest(), count
    if not raw_paths.endswith(b'\0'):
        raise GitStateError('Git returned an unterminated untracked path list')
    entries = raw_paths.split(b'\0')[:-1]
    repo_real = repo_root.resolve(strict=True)
    for raw_path in entries:
        components = raw_path.split(b'/')
        if (
            not raw_path
            or raw_path.startswith(b'/')
            or any(component in {b'', b'.', b'..'} for component in components)
        ):
            raise GitStateError(f'unsafe untracked path in Git evidence: {os.fsdecode(raw_path)!r}')
        names = [os.fsdecode(component) for component in components]
        relative_text = os.fsdecode(raw_path)
        candidate = repo_real.joinpath(*names)
        try:
            candidate.parent.resolve(strict=True).relative_to(repo_real)
        except (OSError, ValueError) as exc:
            raise GitStateError(f'untracked path escapes checkout: {relative_text!r}') from exc

        directory_descriptors: list[int] = []
        directory_names: list[str] = []
        try:
            root_descriptor = os.open(
                repo_real,
                os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0),
            )
            directory_descriptors.append(root_descriptor)
            root_metadata = os.fstat(root_descriptor)
            for name in names[:-1]:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0),
                    dir_fd=directory_descriptors[-1],
                )
                directory_names.append(name)
                directory_descriptors.append(descriptor)
            final_name = names[-1]
            metadata = os.stat(
                final_name,
                dir_fd=directory_descriptors[-1],
                follow_symlinks=False,
            )
            count += 1
            digest.update(len(raw_path).to_bytes(8, 'big'))
            digest.update(raw_path)
            digest.update(stat.S_IFMT(metadata.st_mode).to_bytes(8, 'big'))
            digest.update(stat.S_IMODE(metadata.st_mode).to_bytes(8, 'big'))
            if stat.S_ISLNK(metadata.st_mode):
                target = os.fsencode(os.readlink(final_name, dir_fd=directory_descriptors[-1]))
                digest.update(len(target).to_bytes(8, 'big'))
                digest.update(target)
            elif stat.S_ISREG(metadata.st_mode):
                digest.update(metadata.st_size.to_bytes(8, 'big'))
                descriptor = os.open(
                    final_name,
                    os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
                    dir_fd=directory_descriptors[-1],
                )
                try:
                    opened = os.fstat(descriptor)
                    if opened.st_dev != metadata.st_dev or opened.st_ino != metadata.st_ino:
                        raise GitStateError(
                            f'untracked file changed while collecting evidence: {relative_text!r}'
                        )
                    while True:
                        chunk = os.read(descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                    finished = os.fstat(descriptor)
                    if (
                        finished.st_size != opened.st_size
                        or finished.st_mtime_ns != opened.st_mtime_ns
                        or finished.st_ctime_ns != opened.st_ctime_ns
                    ):
                        raise GitStateError(
                            f'untracked file changed while collecting evidence: {relative_text!r}'
                        )
                finally:
                    os.close(descriptor)
            else:
                raise GitStateError(
                    f'unsupported untracked file type in Git evidence: {relative_text!r}'
                )

            final_metadata = os.stat(
                final_name,
                dir_fd=directory_descriptors[-1],
                follow_symlinks=False,
            )
            if (
                final_metadata.st_dev != metadata.st_dev
                or final_metadata.st_ino != metadata.st_ino
                or final_metadata.st_mode != metadata.st_mode
                or final_metadata.st_size != metadata.st_size
                or final_metadata.st_mtime_ns != metadata.st_mtime_ns
                or final_metadata.st_ctime_ns != metadata.st_ctime_ns
            ):
                raise GitStateError(
                    f'untracked file changed while collecting evidence: {relative_text!r}'
                )
            for index, name in enumerate(directory_names):
                attached = os.stat(
                    name,
                    dir_fd=directory_descriptors[index],
                    follow_symlinks=False,
                )
                opened = os.fstat(directory_descriptors[index + 1])
                if (
                    not stat.S_ISDIR(attached.st_mode)
                    or attached.st_dev != opened.st_dev
                    or attached.st_ino != opened.st_ino
                ):
                    raise GitStateError(
                        f'untracked parent changed while collecting evidence: {relative_text!r}'
                    )
            current_root = repo_real.stat()
            if (
                current_root.st_dev != root_metadata.st_dev
                or current_root.st_ino != root_metadata.st_ino
            ):
                raise GitStateError('checkout root changed while collecting Git evidence')
            candidate.parent.resolve(strict=True).relative_to(repo_real)
        except GitStateError:
            raise
        except (OSError, ValueError) as exc:
            raise GitStateError(
                f'untracked file changed while collecting evidence: {relative_text!r}: {exc}'
            ) from exc
        finally:
            for descriptor in reversed(directory_descriptors):
                os.close(descriptor)
    return digest.hexdigest(), count


def checkout_content_snapshot(repo_root: Path) -> dict[str, Any]:
    """执行对应 Runtime 安全契约，并保持身份、fencing 与 fail-closed 语义。"""
    head = required_value(repo_root, 'rev-parse', 'HEAD')
    status = required_bytes(
        repo_root,
        'status',
        '--porcelain=v1',
        '-z',
        '--untracked-files=all',
    )
    staged = required_bytes(
        repo_root,
        'diff',
        '--cached',
        '--no-ext-diff',
        '--no-textconv',
        '--binary',
        '--full-index',
        '--',
    )
    working = required_bytes(
        repo_root,
        'diff',
        '--no-ext-diff',
        '--no-textconv',
        '--binary',
        '--full-index',
        '--',
    )
    untracked_paths = required_bytes(
        repo_root,
        'ls-files',
        '--others',
        '--exclude-standard',
        '-z',
    )
    untracked_sha, untracked_count = hash_untracked_contents(repo_root, untracked_paths)
    components = {
        'schemaVersion': 1,
        'headCommit': head,
        'statusSha256': hashlib.sha256(status).hexdigest(),
        'stagedDiffSha256': hashlib.sha256(staged).hexdigest(),
        'workingDiffSha256': hashlib.sha256(working).hexdigest(),
        'untrackedContentSha256': untracked_sha,
        'untrackedCount': untracked_count,
    }
    encoded = json.dumps(components, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {**components, 'fingerprint': hashlib.sha256(encoded).hexdigest()}
