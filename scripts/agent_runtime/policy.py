"""Shared agent runtime policy helpers backed by agent-runtime manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


# 维护 repo_root 函数行为。
def repo_root() -> Path:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return Path(__file__).resolve().parents[2]


# 维护 _strip_quotes 函数行为。
def _strip_quotes(value: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


# 维护 _parse_scalar 函数行为。
def _parse_scalar(raw: str) -> Any:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    raw = _strip_quotes(raw.strip())
    if raw in {'', 'null', '~'}:
        return None
    if raw == 'true':
        return True
    if raw == 'false':
        return False
    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(',')]
    try:
        return int(raw)
    except ValueError:
        return raw


# 维护 _parse_top_level_lists 函数行为。
def _parse_top_level_lists(text: str) -> dict[str, list[str]]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    data: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        is_top_level = line == line.lstrip(' ')
        if is_top_level and stripped.endswith(':'):
            current = stripped[:-1]
            data.setdefault(current, [])
            continue
        if is_top_level and ':' in stripped:
            current = None
            continue
        if current and stripped.startswith('- '):
            value = _parse_scalar(stripped[2:].strip())
            if isinstance(value, str):
                data[current].append(value)
            continue
        if current and is_top_level:
            current = None
    return data


# 维护 load_runtime_manifest 函数行为。
def load_runtime_manifest(root: Path | None = None) -> dict[str, Any]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    base = Path(root) if root is not None else repo_root()
    manifest_path = base / 'harness' / 'agent-runtime.manifest.yaml'
    if not manifest_path.is_file():
        raise FileNotFoundError(f'runtime manifest not found: {manifest_path}')
    text = manifest_path.read_text(encoding='utf-8')
    lists = _parse_top_level_lists(text)
    return {
        'protected_roots': lists.get('protected_roots', []),
        'required_gates': lists.get('required_gates', []),
        '_path': str(manifest_path),
    }


# 维护 _normalize_root 函数行为。
def _normalize_root(value: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    root = normalize_repo_path(value)
    if value.endswith('/') and root and not root.endswith('/'):
        root += '/'
    return root


# 维护 protected_roots 函数行为。
def protected_roots(root: Path | None = None) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    roots = load_runtime_manifest(root).get('protected_roots', [])
    if not isinstance(roots, list):
        return []
    result: list[str] = []
    for item in roots:
        if not isinstance(item, str) or not item.strip():
            continue
        normalized = _normalize_root(item.strip())
        if normalized and normalized not in result:
            result.append(normalized)
    return result


# 维护 normalize_repo_path 函数行为。
def normalize_repo_path(path: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    raw = str(path).strip().replace('\\', '/')
    if not raw:
        return ''
    raw = raw.removeprefix('file://')
    candidate = Path(raw).expanduser()
    try:
        if candidate.is_absolute():
            rel = candidate.resolve().relative_to(repo_root().resolve())
            raw = rel.as_posix()
    except (OSError, ValueError):
        raw = candidate.as_posix()
    while raw.startswith('./'):
        raw = raw[2:]
    parts: list[str] = []
    for part in raw.split('/'):
        if part in {'', '.'}:
            continue
        if part == '..':
            if parts:
                parts.pop()
            else:
                parts.append(part)
            continue
        parts.append(part)
    normalized = '/'.join(parts)
    if raw.endswith('/') and normalized and not normalized.endswith('/'):
        normalized += '/'
    return normalized


# 维护 _normalize_repo_path_for_root 函数行为。
def _normalize_repo_path_for_root(path: str, root: Path | None = None) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    raw = str(path).strip().replace('\\', '/')
    if not raw:
        return ''
    raw = raw.removeprefix('file://')
    base = Path(root) if root is not None else repo_root()
    candidate = Path(raw).expanduser()
    try:
        if candidate.is_absolute():
            raw = candidate.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        raw = candidate.as_posix()
    return normalize_repo_path(raw)


# 维护 is_protected_path 函数行为。
def is_protected_path(path: str, root: Path | None = None) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    normalized = _normalize_repo_path_for_root(path, root)
    if not normalized or normalized.startswith('../') or normalized == '..':
        return False
    for protected in protected_roots(root):
        clean = protected.rstrip('/')
        if normalized == clean or normalized.startswith(f'{clean}/'):
            return True
    return False


# 维护 required_platforms 函数行为。
def required_platforms(root: Path | None = None) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    base = Path(root) if root is not None else repo_root()
    manifest_path = base / 'harness' / 'agent-runtime.manifest.yaml'
    text = manifest_path.read_text(encoding='utf-8')
    platforms: list[str] = []
    in_platforms = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == 'platforms:':
            in_platforms = True
            continue
        if in_platforms:
            if line and not line.startswith(' '):
                break
            if line.startswith('  ') and not line.startswith('    ') and stripped.endswith(':'):
                platforms.append(stripped[:-1])
    return platforms


# 维护 main 函数行为。
def main(argv: list[str] | None = None) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    parser = argparse.ArgumentParser(description='Agent runtime policy helper')
    parser.add_argument('--is-protected', metavar='PATH', help='check whether PATH is protected')
    parser.add_argument('--list-protected-roots', action='store_true')
    parser.add_argument('--root', default=None, help='repository root override')
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else None
    if args.list_protected_roots:
        for item in protected_roots(root):
            print(item)
        return 0
    if args.is_protected is not None:
        return 0 if is_protected_path(args.is_protected, root) else 1
    parser.print_help()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
