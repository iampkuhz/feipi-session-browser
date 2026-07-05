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


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def exists(path: Path) -> tuple[bool, str]:
    rel = path.relative_to(ROOT) if path.exists() or ROOT in path.parents else path
    return path.exists(), f'exists: {rel}' if path.exists() else f'MISSING: {rel}'


def has(text: str, needle: str) -> tuple[bool, str]:
    return needle in text, f'found {needle!r}' if needle in text else f'MISSING {needle!r}'


def has_all(text: str, needles: Iterable[str]) -> tuple[bool, str]:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        return False, 'MISSING: ' + ', '.join(repr(item) for item in missing)
    return True, 'all present'


def has_none(text: str, needles: Iterable[str]) -> tuple[bool, str]:
    present = [needle for needle in needles if needle in text]
    if present:
        return False, 'unexpected: ' + ', '.join(repr(item) for item in present)
    return True, 'clean'


def run(title: str, checks: list[Check]) -> int:
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
