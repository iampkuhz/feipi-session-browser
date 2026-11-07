"""一次加载 Agent policy 文档并检查大小、受保护路径与 handoff 协议。

共用文档快照可以避免各规则重复读取文件，并保证一次检查始终针对同一份内容。
公开入口 ``check(arguments)`` 先建立单次文档快照，再按体积、路径和交接协议顺序汇总诊断。输入不可读取
时返回 FAIL；文档已完整读取但不符合政策时返回 BLOCKED。
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml
from scripts.gates.checks.check_protocol import CheckResult, argument_parser, repository_root

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
    'src/session_browser/',
    'scripts/tests/',
    'java/tests/',
    'AGENTS.md',
    '.claude/CLAUDE.md',
]
MAIN_DOCS = {
    'Claude main': '.claude/agents/qwen-main-default.md',
    'Codex model': '.codex/model-instructions.md',
}
HANDOFF_CONTRACT = (
    'skills/authoring/feipi-openspec-orchestrate-change/references/subagent-contract.md'
)
PROTOCOL_DOCS = {
    'shared handoff': HANDOFF_CONTRACT,
    '.claude/CLAUDE.md': '.claude/CLAUDE.md',
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
    documents = {
        relative: (root / relative).read_text(encoding='utf-8')
        for relative in PROTOCOL_DOCS.values()
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


def _manifest_roots(manifest: object) -> list[str]:
    """从已解析 manifest 提取受保护路径。"""

    roots = manifest.get('protected_roots', []) if isinstance(manifest, dict) else []
    normalized_roots: list[str] = []
    for value in roots if isinstance(roots, list) else []:
        if not isinstance(value, str):
            continue
        normalized = _normalize_repo_path(value)
        if value.endswith('/') and normalized and not normalized.endswith('/'):
            normalized += '/'
        if normalized and normalized not in normalized_roots:
            normalized_roots.append(normalized)
    return normalized_roots


def _check_required_manifest_roots(roots: list[str]) -> list[str]:
    """检查 manifest 是否登记全部受保护根路径。"""
    return [
        f'agent-policy manifest protected_roots 缺少必需项: {root}'
        for root in POLICY_REQUIRED_ROOTS
        if root not in roots
    ]


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


def _check_handoff(inputs: DocumentInputs) -> list[str]:
    """检查平台引用及共享 handoff 的字段、隔离和结果语义。"""
    errors: list[str] = []
    # 平台只负责把执行者导向共享真源，不再强迫复制全部协议字段。
    for label, relative in {**MAIN_DOCS, 'Claude entry': '.claude/CLAUDE.md'}.items():
        text = inputs.documents[relative]
        for reference in (HANDOFF_CONTRACT, 'harness/agent-policy.manifest.yaml'):
            if reference not in text:
                errors.append(f'{label} missing shared protocol reference: {reference}')
    manifest = inputs.manifest if isinstance(inputs.manifest, dict) else {}
    protocol = manifest.get('subagent_instance_protocol', {})
    if not isinstance(protocol, dict):
        protocol = {}
    for key, expected in (
        ('required_handoff_fields', REQUIRED_HANDOFF_FIELDS),
        ('required_output_fields', REQUIRED_OUTPUT_FIELDS),
        ('status_values', ['PASS', 'FAIL', 'BLOCKED']),
    ):
        if protocol.get(key) != expected:
            errors.append(f'policy manifest invalid subagent_instance_protocol.{key}')
    shared = inputs.documents[HANDOFF_CONTRACT]
    for field in [*REQUIRED_HANDOFF_FIELDS, *REQUIRED_OUTPUT_FIELDS, 'PASS', 'FAIL', 'BLOCKED']:
        if field not in shared:
            errors.append(f'shared handoff missing field: {field}')
    # 两份共享表示各有读者，隔离约束必须同时存在，不能只验证入口链接。
    identity = protocol.get('identity_rules', [])
    identity_text = '\n'.join(str(rule) for rule in identity) if isinstance(identity, list) else ''
    for label, text in (('shared handoff', shared), ('policy identity_rules', identity_text)):
        for term in ('Task id', 'agent_id', 'client/session_id', '不重叠', '静默跳过'):
            if term not in text:
                errors.append(f'{label} missing isolation rule: {term}')
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
    return CheckResult.from_errors(
        [
            *_check_sizes(inputs),
            *_check_required_manifest_roots(_manifest_roots(inputs.manifest)),
            *_check_handoff(inputs),
        ]
    )
