#!/usr/bin/env python3
"""Shared helpers for Java API-first static QA scripts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JAVA_RESOURCES = ROOT / 'java/web/src/main/resources'
TEMPLATES = JAVA_RESOURCES / 'templates'
STATIC = JAVA_RESOURCES / 'static'
CSS = STATIC / 'css'
JS = STATIC / 'js'

LEGACY_PY_ROOT = 'src/' + 'session_browser'
LEGACY_TEMPLATE_ROOT = 'session_browser/web/' + 'templates'
LEGACY_STATIC_ROOT = 'session_browser/web/' + 'static'
LEGACY_ROUND_TOKEN_ATTR = 'data-round-' + 'tokens'

Check = tuple[str, Callable[[], tuple[bool, str]]]


# 读取文本文件内容。
def read(path: Path) -> str:
    """参数：
        path: 待读取的文件路径。

    返回：
        文件文本；文件不存在时返回空字符串。
    """
    return path.read_text(encoding='utf-8') if path.exists() else ''


# 检查路径是否存在。
def exists(path: Path) -> tuple[bool, str]:
    """参数：
        path: 待检查的路径。

    返回：
        是否存在和说明文本。
    """
    rel = path.relative_to(ROOT) if path.exists() or ROOT in path.parents else path
    return path.exists(), f'exists: {rel}' if path.exists() else f'MISSING: {rel}'


# 检查文本是否包含指定片段。
def has(text: str, needle: str) -> tuple[bool, str]:
    """参数：
        text: 待检查文本。
        needle: 必须出现的片段。

    返回：
        是否包含和说明文本。
    """
    return needle in text, f'found {needle!r}' if needle in text else f'MISSING {needle!r}'


# 检查文本是否包含所有片段。
def has_all(text: str, needles: Iterable[str]) -> tuple[bool, str]:
    """参数：
        text: 待检查文本。
        needles: 必须出现的片段集合。

    返回：
        是否全部包含和说明文本。
    """
    missing = [needle for needle in needles if needle not in text]
    if missing:
        return False, 'MISSING: ' + ', '.join(repr(item) for item in missing)
    return True, 'all present'


# 检查文本是否不包含任一片段。
def has_none(text: str, needles: Iterable[str]) -> tuple[bool, str]:
    """参数：
        text: 待检查文本。
        needles: 禁止出现的片段集合。

    返回：
        是否全部未出现和说明文本。
    """
    present = [needle for needle in needles if needle in text]
    if present:
        return False, 'unexpected: ' + ', '.join(repr(item) for item in present)
    return True, 'clean'


# 运行一组 QA 检查。
def run(title: str, checks: list[Check]) -> int:
    """参数：
        title: 检查标题。
        checks: 检查项列表。

    返回：
        进程退出码。
    """
    failures: list[str] = []
    print(f'{title}')
    for label, fn in checks:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 - QA scripts should surface checker failures.
            ok, detail = False, f'checker raised {type(exc).__name__}: {exc}'
        status = 'PASS' if ok else 'FAIL'
        print(f'  [{status}] {label}: {detail}')
        if not ok:
            failures.append(label)
    if failures:
        print(f'\nFAIL: {title} ({len(failures)} failed)')
        return 1
    print(f'\nPASS: {title}')
    return 0
