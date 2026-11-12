"""一次加载 Agent policy 文档并检查大小、受保护路径与 handoff 协议。

共用文档快照可以避免各规则重复读取文件，并保证一次检查始终针对同一份内容。
公开入口 ``check(arguments)`` 先建立单次文档快照，再按体积、路径和交接协议顺序汇总诊断。输入不可读取
时返回 FAIL；文档已完整读取但不符合政策时返回 BLOCKED。
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass

import yaml
from scripts.gates.checks.check_protocol import CheckResult, argument_parser, repository_root

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
MULTICA_BEGIN = '<!-- BEGIN MULTICA-RUNTIME (auto-managed; do not edit) -->'
MULTICA_END = '<!-- END MULTICA-RUNTIME -->'
MULTICA_IDENTITY_KEYS = (
    'MULTICA_TOKEN',
    'MULTICA_TASK_ID',
    'MULTICA_AGENT_ID',
    'MULTICA_WORKSPACE_ID',
    'MULTICA_SERVER_URL',
)
MULTICA_UUID_PATTERN = r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'


def _has_runtime_marker(text: str) -> bool:
    """识别不完整或被修改的原生标记，不输出注入内容。"""
    return 'MULTICA-RUNTIME' in text


@dataclass(frozen=True)
class DocumentInputs:
    """保存每份 policy 文档的一次读取结果。"""

    manifest: object
    agents_text: str
    codex_config: object
    documents: dict[str, str]


def _load_document_inputs() -> DocumentInputs:
    """一次读取 manifest、AGENTS、Codex config 和各 handoff 文档。"""

    root = ROOT
    manifest_text = (root / 'harness/agent-policy.manifest.yaml').read_text(encoding='utf-8')
    agents_text = (root / 'AGENTS.md').read_bytes().decode('utf-8')
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


def _git_runtime_errors() -> list[str]:
    """读取提交和暂存源码身份，不记录文档内容。"""
    errors: list[str] = []
    for revision in ('HEAD:AGENTS.md', ':AGENTS.md'):
        try:
            result = subprocess.run(
                ['git', '-C', str(ROOT), 'show', revision],
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise OSError(f'AGENTS.md Git source unavailable: {revision}') from None
        if result.returncode:
            raise OSError(f'AGENTS.md Git source unavailable: {revision}')
        try:
            text = result.stdout.decode('utf-8')
        except UnicodeDecodeError:
            raise OSError(f'AGENTS.md Git source unreadable: {revision}') from None
        if _has_runtime_marker(text):
            errors.append(f'AGENTS.md runtime marker forbidden in Git source: {revision}')
    return errors


def _runtime_source(text: str) -> tuple[str, str, list[str]]:
    """仅拆分环境一致的严格原生尾块，不暴露注入内容。"""
    if not _has_runtime_marker(text):
        return text, '', []
    if not all(os.environ.get(key, '').strip() for key in MULTICA_IDENTITY_KEYS):
        return text, '', ['AGENTS.md runtime block requires complete Multica task identity']
    if not all(
        re.fullmatch(MULTICA_UUID_PATTERN, os.environ[key])
        for key in (
            'MULTICA_TASK_ID',
            'MULTICA_AGENT_ID',
            'MULTICA_WORKSPACE_ID',
        )
    ):
        return text, '', ['AGENTS.md runtime block has invalid Multica task identity']
    if text.count(MULTICA_BEGIN) != 1 or text.count(MULTICA_END) != 1:
        return text, '', ['AGENTS.md malformed runtime markers']
    before, _, after = text.partition(MULTICA_BEGIN)
    if not before.endswith('\n\n'):
        return text, '', ['AGENTS.md runtime block requires exact separator']
    if not after.endswith('\n' + MULTICA_END + '\n'):
        return text, '', ['AGENTS.md runtime block must be a complete terminal suffix']
    body = after[1 : -(len(MULTICA_END) + 2)]
    # 原生首行边界元数据仅允许转义换行；完整原文仍计入 runtime 字节预算。
    body = re.sub(
        r'\A<!-- MULTICA-RUNTIME original-boundary: "(?:\\[nr])*" -->\n', '', body, count=1
    )
    if (
        not after.startswith('\n')
        or not body.strip()
        or body.endswith('\n')
        or _has_runtime_marker(body)
        or _has_runtime_marker(before)
    ):
        return text, '', ['AGENTS.md malformed runtime body']
    return before[:-2], text[len(before) - 2 :], []


def _check_sizes(inputs: DocumentInputs) -> list[str]:
    """分别约束维护源码和环境一致的临时尾块，并核对完整加载预算。"""
    manifest = inputs.manifest if isinstance(inputs.manifest, dict) else {}
    limits = manifest.get('size_limits', {})
    if not isinstance(limits, dict) or not isinstance(limits.get('AGENTS.md'), int):
        return ['policy manifest size_limits 缺少 AGENTS.md 限制']
    source, runtime, errors = _runtime_source(inputs.agents_text)
    errors.extend(_git_runtime_errors())
    size = len(source.encode('utf-8'))
    physical_size = len(inputs.agents_text.encode('utf-8'))
    limit = limits['AGENTS.md']
    if size > limit:
        errors.append(f'AGENTS.md {size} bytes 超过限制 {limit} bytes')
    if runtime:
        runtime_limit = limits.get('multica_runtime_bytes')
        if type(runtime_limit) is not int or runtime_limit <= 0:
            errors.append('policy manifest size_limits 缺少有效 multica_runtime_bytes 限制')
        elif len(runtime.encode('utf-8')) > runtime_limit:
            errors.append(f'AGENTS.md runtime block 超过限制 {runtime_limit} bytes')
    codex_max = inputs.codex_config.get('project_doc_max_bytes')
    if (runtime or codex_max is not None) and (
        type(codex_max) is not int or codex_max < physical_size + 100
    ):
        errors.append(
            '.codex/config.toml project_doc_max_bytes insufficient: '
            f'AGENTS.md physical size({physical_size}) + 100 required'
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
        inputs = _load_document_inputs()
        size_errors = _check_sizes(inputs)
    except OSError as exc:
        return CheckResult.execution_failure(
            [f'Agent document 输入读取失败: {exc}'], reason='input-unavailable'
        )
    except (yaml.YAMLError, tomllib.TOMLDecodeError) as exc:
        return CheckResult.from_errors([f'Agent document 配置内容无效: {exc}'])
    return CheckResult.from_errors(
        [
            *size_errors,
            *_check_required_manifest_roots(_manifest_roots(inputs.manifest)),
            *_check_handoff(inputs),
        ]
    )
