#!/usr/bin/env python3
"""检查共享 Agent policy 与 AGENTS.md 的受保护路径声明。

完整的受保护路径可避免治理文件在普通修改中被意外覆盖。公开入口是 `check(arguments)`；
返回诊断表示 manifest 或入口文档遗漏了必需路径。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from scripts.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
POLICY_MANIFEST = ROOT / 'harness' / 'agent-policy.manifest.yaml'
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


def _normalize_repo_path(value: str) -> str:
    normalized = value.strip().replace('\\', '/')
    if normalized.startswith('./'):
        normalized = normalized[2:]
    while '//' in normalized:
        normalized = normalized.replace('//', '/')
    return normalized


def _manifest_roots(root: Path = ROOT) -> list[str]:
    """读取并规范化 protected_roots；解析失败返回空列表交由调用方关闭式失败。"""
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


def _check_required_manifest_roots(roots: list[str]) -> list[str]:
    """检查共享 manifest 是否覆盖最小受保护根目录集合。"""
    return [
        f'agent-policy manifest protected_roots 缺少必需项: {root}'
        for root in POLICY_REQUIRED_ROOTS
        if root not in roots
    ]


def _check_agents_doc_covers_required_roots(root: Path = ROOT) -> list[str]:
    """检查 AGENTS.md 是否继续声明产品、测试及治理目录的完整保护范围。"""
    try:
        text = (root / 'AGENTS.md').read_text(encoding='utf-8')
    except OSError as exc:
        return [f'无法读取 AGENTS.md: {exc}']
    return [
        f'AGENTS.md 缺少 protected_root: {required}'
        for required in DOCUMENTED_REQUIRED_ROOTS
        if required not in text
    ]


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回受保护路径交叉检查结果。"""
    parser = argument_parser(description='检查 Agent policy 受保护路径')
    parser.parse_args(arguments)
    roots = _manifest_roots(ROOT)
    errors = _check_required_manifest_roots(roots)
    errors.extend(_check_agents_doc_covers_required_roots(ROOT))
    return CheckResult.from_errors(errors)
