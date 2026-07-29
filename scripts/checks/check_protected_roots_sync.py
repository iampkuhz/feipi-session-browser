#!/usr/bin/env python3
"""检查共享 agent policy 的受保护路径声明；不依赖 Hook/Session Runtime。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from scripts.checks._framework import repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
POLICY_MANIFEST = ROOT / 'harness' / 'agent-policy.manifest.yaml'
GATE_NAME = 'protectedRootsSync'

POLICY_REQUIRED_ROOTS = [
    '.claude/',
    '.codex/',
    '.qoder/',
    '.agents/',
    'skills/',
    'harness/',
    'scripts/',
    'openspec/',
    'AGENTS.md',
    'CLAUDE.md',
]
DOCUMENTED_REQUIRED_ROOTS = [
    *POLICY_REQUIRED_ROOTS[:-2],
    'src/session_browser/',
    'tests/',
    *POLICY_REQUIRED_ROOTS[-2:],
]
OMISSION_SENTINELS = ['.agents/', 'skills/', 'tests/']


def fail(errors: list[str]) -> int:
    """输出全部失败原因并返回非零状态。"""
    for error in errors:
        print(f'[{GATE_NAME}] FAIL: {error}')
    return 1


def _normalize_repo_path(value: str) -> str:
    normalized = value.strip().replace('\\', '/')
    if normalized.startswith('./'):
        normalized = normalized[2:]
    while '//' in normalized:
        normalized = normalized.replace('//', '/')
    return normalized


def manifest_roots(root: Path = ROOT) -> list[str]:
    """读取共享 policy manifest 的 protected_roots，解析失败时返回空列表。"""
    path = root / 'harness' / 'agent-policy.manifest.yaml'
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError):
        return []
    values = data.get('protected_roots', []) if isinstance(data, dict) else []
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, str):
            continue
        normalized = _normalize_repo_path(value)
        if value.endswith('/') and normalized and not normalized.endswith('/'):
            normalized += '/'
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def check_required_manifest_roots(roots: list[str]) -> list[str]:
    """确保共享 policy manifest 没有遗漏其最小受保护根目录。"""
    return [
        f'agent-policy manifest protected_roots 缺少必需项: {root}'
        for root in POLICY_REQUIRED_ROOTS
        if root not in roots
    ]


def check_agents_doc_covers_required_roots(root: Path = ROOT) -> list[str]:
    """确保工程入口规则继续声明产品与测试等完整受保护范围。"""
    try:
        text = (root / 'AGENTS.md').read_text(encoding='utf-8')
    except OSError as exc:
        return [f'无法读取 AGENTS.md: {exc}']
    return [
        f'AGENTS.md 缺少 protected_root: {required}'
        for required in DOCUMENTED_REQUIRED_ROOTS
        if required not in text
    ]


def main() -> int:
    """运行共享 agent policy 受保护路径检查。"""
    roots = manifest_roots(ROOT)
    errors = check_required_manifest_roots(roots)
    errors.extend(check_agents_doc_covers_required_roots(ROOT))
    if errors:
        return fail(errors)
    print(f'[{GATE_NAME}] PASS')
    return 0
