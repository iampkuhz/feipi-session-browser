"""一次加载 Agent policy 文档并检查大小、受保护路径与 handoff 协议。

共用文档快照可以避免各规则重复读取文件，并保证一次检查始终针对同一份内容。
公开入口 ``check(arguments)`` 先建立单次文档快照，再按体积、路径和交接协议顺序汇总诊断。输入不可读取
时返回 FAIL；文档已完整读取但不符合政策时返回 BLOCKED。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml
from scripts.gates.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
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
MAIN_DOCS = {
    'Claude main': '.claude/agents/qwen-main-default.md',
    'Qoder main': '.qoder/agents/qoder-main-default.md',
    'Codex model': '.codex/model-instructions.md',
}
SKIP_POLICY_DOCS = {
    'AGENTS.md': 'AGENTS.md',
    'CLAUDE.md': 'CLAUDE.md',
    '.qoder/AGENTS.md': '.qoder/AGENTS.md',
    **MAIN_DOCS,
}
REQUIRED_HANDOFF_FIELDS = [
    'Goal',
    'Task id',
    'Task source',
    'Allowed files/directories',
    'Forbidden files/directories',
    'Required context files',
    'Expected output',
    'Validation command',
    'Failure policy',
]
REQUIRED_OUTPUT_FIELDS = ['Status', 'Changed files', 'Validation', 'Effect checks', 'Risks']


@dataclass(frozen=True)
class DocumentInputs:
    """保存每份 policy 文档的一次读取结果。"""

    manifest: object
    agents_text: str
    codex_config: object
    documents: dict[str, str]


def _load_document_inputs(root: Path = ROOT) -> DocumentInputs:
    """一次读取 manifest、AGENTS、Codex config 和各 handoff 文档。"""

    manifest_text = (root / 'harness/agent-policy.manifest.yaml').read_text(encoding='utf-8')
    agents_text = (root / 'AGENTS.md').read_text(encoding='utf-8')
    paths = set(SKIP_POLICY_DOCS.values()) - {'AGENTS.md'}
    documents = {
        relative: (root / relative).read_text(encoding='utf-8') for relative in sorted(paths)
    }
    return DocumentInputs(
        manifest=yaml.safe_load(manifest_text),
        agents_text=agents_text,
        codex_config=tomllib.loads((root / '.codex/config.toml').read_text(encoding='utf-8')),
        documents=documents,
    )


def _normalize_repo_path(value: str) -> str:
    """把 manifest 路径统一为仓库相对的正斜杠形式。"""
    normalized = value.strip().replace('\\', '/')
    if normalized.startswith('./'):
        normalized = normalized[2:]
    while '//' in normalized:
        normalized = normalized.replace('//', '/')
    return normalized


def _manifest_policy(manifest: object) -> tuple[list[str], list[str]]:
    """从已解析 manifest 提取受保护路径与必需短语。"""

    roots = manifest.get('protected_roots', []) if isinstance(manifest, dict) else []
    phrases = manifest.get('required_phrases', []) if isinstance(manifest, dict) else []
    normalized_roots: list[str] = []
    for value in roots if isinstance(roots, list) else []:
        if not isinstance(value, str):
            continue
        normalized = _normalize_repo_path(value)
        if value.endswith('/') and normalized and not normalized.endswith('/'):
            normalized += '/'
        if normalized and normalized not in normalized_roots:
            normalized_roots.append(normalized)
    normalized_phrases = [
        value.strip()
        for value in phrases
        if isinstance(phrases, list) and isinstance(value, str) and value.strip()
    ]
    return normalized_roots, normalized_phrases


def _check_required_manifest_roots(roots: list[str]) -> list[str]:
    """检查 manifest 是否登记全部受保护根路径。"""
    return [
        f'agent-policy manifest protected_roots 缺少必需项: {root}'
        for root in POLICY_REQUIRED_ROOTS
        if root not in roots
    ]


def _check_agents_doc(text: str, required_phrases: list[str]) -> list[str]:
    """检查 AGENTS.md 是否展示受保护路径与必需短语。"""
    errors = [
        f'AGENTS.md 缺少 protected_root: {required}'
        for required in DOCUMENTED_REQUIRED_ROOTS
        if required not in text
    ]
    if not required_phrases:
        errors.append('agent-policy manifest required_phrases 不能为空')
    errors.extend(
        f'AGENTS.md 缺少 required phrase: {phrase!r}'
        for phrase in required_phrases
        if phrase not in text
    )
    return errors


def _check_sizes(inputs: DocumentInputs) -> list[str]:
    """用同一份 AGENTS 文本检查 manifest 与 Codex 的体积上限。"""
    manifest = inputs.manifest if isinstance(inputs.manifest, dict) else {}
    limits = manifest.get('size_limits', {})
    if not isinstance(limits, dict) or not isinstance(limits.get('AGENTS.md'), int):
        return ['policy manifest size_limits 缺少 AGENTS.md 限制']
    size = len(inputs.agents_text.encode('utf-8'))
    limit = limits['AGENTS.md']
    errors = [f'AGENTS.md {size} bytes 超过限制 {limit} bytes'] if size > limit else []
    codex_max = inputs.codex_config.get('project_doc_max_bytes')
    if codex_max is not None and (not isinstance(codex_max, int) or codex_max < size + 100):
        errors.append(
            f'.codex/config.toml project_doc_max_bytes={codex_max} '
            f'< AGENTS.md size({size}) + 100 = {size + 100}'
        )
    return errors


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    """判断文本是否包含任一政策术语。"""
    return any(term in text for term in terms)


def _contains_skipped_can_pass(text: str) -> bool:
    """识别把 skipped 错误描述为可 PASS 的政策措辞。"""
    patterns = [
        r'(skipped|跳过).{0,24}(can|may|可以|可|能|算|视为).{0,24}(PASS|pass|通过)',
        r'(PASS|pass|通过).{0,24}(can|may|可以|可|能|算|视为).{0,24}(skipped|跳过)',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            window = text[max(0, match.start() - 20) : match.end() + 20]
            if not _has_any(window, ('不得', '不能', '不算', 'non-PASS', 'not PASS')):
                return True
    return False


def _check_handoff(inputs: DocumentInputs) -> list[str]:
    """检查三端 handoff 字段、实例隔离、证据归属和结果语义。"""
    errors: list[str] = []
    for label, relative in MAIN_DOCS.items():
        text = inputs.documents[relative]
        missing = [field for field in REQUIRED_HANDOFF_FIELDS if field not in text]
        if missing:
            errors.append(f'{label} missing handoff fields: {", ".join(missing)}')
        missing_output = [field for field in REQUIRED_OUTPUT_FIELDS if field not in text]
        if missing_output:
            errors.append(f'{label} missing output fields: {", ".join(missing_output)}')
        if not _has_any(text, ('agent_id', 'instance id')):
            errors.append(f'{label} missing unique agent_id/instance id rule')
        if not (_has_any(text, ('client/session_id', 'evidence')) and 'session_id' in text):
            errors.append(f'{label} missing same client/session_id evidence aggregation rule')
        if not _has_any(text, ('不重叠', 'non-overlapping')):
            errors.append(f'{label} missing non-overlapping parallel write scope rule')
        if not _has_any(text, ('静默跳过 validation', 'silently skip validation')):
            errors.append(f'{label} missing subagent failure cannot skip validation rule')
    manifest_text = yaml.safe_dump(inputs.manifest, allow_unicode=True)
    status_docs = {
        'policy manifest': manifest_text,
        **{label: inputs.documents[relative] for label, relative in MAIN_DOCS.items()},
    }
    errors.extend(
        f'{label} missing status values PASS/FAIL/BLOCKED'
        for label, text in status_docs.items()
        if not all(re.search(rf'\b{status}\b', text) for status in ('PASS', 'FAIL', 'BLOCKED'))
    )
    policy_texts = {
        'AGENTS.md': inputs.agents_text,
        **{
            label: inputs.documents[relative]
            for label, relative in SKIP_POLICY_DOCS.items()
            if relative != 'AGENTS.md'
        },
    }
    errors.extend(
        f'{label} contains skipped-can-PASS wording'
        for label, text in policy_texts.items()
        if _contains_skipped_can_pass(text)
    )
    if not isinstance(inputs.manifest, dict) or 'subagent_instance_protocol' not in inputs.manifest:
        errors.append('policy manifest missing subagent_instance_protocol')
    return errors


def check(arguments: list[str]) -> CheckResult:
    """返回 policy size、protected roots 与 subagent handoff 的合并结论。"""

    argument_parser(description='检查 Agent document policy').parse_args(arguments)
    try:
        inputs = _load_document_inputs(ROOT)
    except OSError as exc:
        return CheckResult.execution_failure(
            [f'Agent document 输入读取失败: {exc}'], reason='input-unavailable'
        )
    except (yaml.YAMLError, tomllib.TOMLDecodeError) as exc:
        return CheckResult.from_errors([f'Agent document 配置内容无效: {exc}'])
    roots, phrases = _manifest_policy(inputs.manifest)
    return CheckResult.from_errors(
        [
            *_check_sizes(inputs),
            *_check_required_manifest_roots(roots),
            *_check_agents_doc(inputs.agents_text, phrases),
            *_check_handoff(inputs),
        ]
    )
