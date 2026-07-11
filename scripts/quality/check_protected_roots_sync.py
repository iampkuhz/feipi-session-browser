#!/usr/bin/env python3
"""Check that protected roots stay synchronized with the runtime manifest."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_runtime import policy as runtime_policy  # noqa: E402

GATE_NAME = 'protectedRootsSync'
REQUIRED_ROOTS = [
    '.claude/',
    '.codex/',
    '.qoder/',
    '.agents/',
    'skills/',
    'harness/',
    'scripts/',
    'openspec/',
    'src/session_browser/',
    'tests/',
    'AGENTS.md',
    'CLAUDE.md',
]
OMISSION_SENTINELS = ['.agents/', 'skills/', 'tests/']


# 维护 fail 函数行为。
def fail(errors: list[str]) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    for error in errors:
        print(f'[{GATE_NAME}] FAIL: {error}')
    return 1


# 维护 manifest_roots 函数行为。
def manifest_roots(root: Path = ROOT) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return runtime_policy.protected_roots(root)


# 维护 _normalize_roots 函数行为。
def _normalize_roots(values: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    result: list[str] = []
    for value in values:
        normalized = runtime_policy.normalize_repo_path(value)
        if value.endswith('/') and normalized and not normalized.endswith('/'):
            normalized += '/'
        if normalized not in result:
            result.append(normalized)
    return result


# 维护 check_required_manifest_roots 函数行为。
def check_required_manifest_roots(roots: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    missing = [root for root in REQUIRED_ROOTS if root not in roots]
    errors = [f'manifest protected_roots 缺少必需项: {root}' for root in missing]
    for root in OMISSION_SENTINELS:
        if root not in roots:
            errors.append(f'sync gate sentinel missing root detected: {root}')
    return errors


# 维护 _read 函数行为。
def _read(rel: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return (ROOT / rel).read_text(encoding='utf-8')


# 维护 _literal_protected_roots_assignment 函数行为。
def _literal_protected_roots_assignment(text: str) -> list[str] | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == 'PROTECTED_ROOTS' for target in node.targets):
            continue
        if isinstance(node.value, ast.List):
            values: list[str] = []
            for item in node.value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    values.append(item.value)
                else:
                    return None
            return _normalize_roots(values)
        return None
    return None


# 维护 check_stop_check_uses_helper 函数行为。
def check_stop_check_uses_helper(roots: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read('scripts/harness/stop_helpers.py')
    errors: list[str] = []
    if 'runtime_policy.is_protected_path' not in text:
        literal = _literal_protected_roots_assignment(text)
        if literal is None:
            errors.append('stop_helpers.py 未使用 runtime policy helper 读取 protected roots')
        elif literal != roots:
            errors.append('stop_helpers.py PROTECTED_ROOTS 与 manifest 不一致')
    for sentinel in OMISSION_SENTINELS:
        if sentinel not in roots:
            errors.append(f'stop_helpers.py sync sentinel would miss: {sentinel}')
    return errors


# 维护 _extract_shell_array 函数行为。
def _extract_shell_array(text: str, name: str) -> list[str] | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    match = re.search(rf'{re.escape(name)}=\((.*?)\)', text, flags=re.S)
    if not match:
        return None
    return re.findall(r'["\']([^"\']+)["\']', match.group(1))


# 维护 check_shell_hooks_use_helper 函数行为。
def check_shell_hooks_use_helper(roots: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    errors: list[str] = []
    for rel in ['.codex/hooks/pre_write_guard.sh', '.qoder/hooks/pre_write_guard.sh']:
        text = _read(rel)
        array_values = _extract_shell_array(text, 'PROTECTED_ROOTS')
        if array_values is not None and _normalize_roots(array_values) != roots:
            errors.append(f'{rel} PROTECTED_ROOTS hardcoded array 与 manifest 不一致')
        if array_values is not None and 'scripts.agent_runtime.policy' not in text:
            errors.append(f'{rel} 维护 hardcoded protected roots 且未调用 runtime policy helper')
    return errors


# 维护 check_report_gate_uses_helper 函数行为。
def check_report_gate_uses_helper() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read('scripts/quality/check_agent_runtime_report.py')
    if 'runtime_policy.protected_roots' in text and 'runtime_policy.is_protected_path' in text:
        return []
    return ['check_agent_runtime_report.py 未使用 runtime policy helper']


# 维护 check_rules_sync_uses_helper 函数行为。
def check_rules_sync_uses_helper() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read('scripts/quality/check_agent_rules_sync.py')
    if 'runtime_policy.protected_roots' in text:
        return []
    return ['check_agent_rules_sync.py 未使用 runtime policy helper']


# 维护 check_agents_doc_covers_manifest 函数行为。
def check_agents_doc_covers_manifest(roots: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read('AGENTS.md')
    return [f'AGENTS.md 缺少 protected_root: {root}' for root in roots if root not in text]


# 维护 main 函数行为。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    roots = manifest_roots(ROOT)
    errors: list[str] = []
    errors.extend(check_required_manifest_roots(roots))
    errors.extend(check_agents_doc_covers_manifest(roots))
    errors.extend(check_stop_check_uses_helper(roots))
    errors.extend(check_shell_hooks_use_helper(roots))
    errors.extend(check_report_gate_uses_helper())
    errors.extend(check_rules_sync_uses_helper())
    if errors:
        return fail(errors)
    print(f'[{GATE_NAME}] PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
