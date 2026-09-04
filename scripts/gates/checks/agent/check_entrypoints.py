"""一次加载 Agent runtime 输入并检查跨平台入口与权限政策。

共享输入必须只读取一次，用于避免同一次检查中的不同规则看到不一致状态。
维护者只需从公开入口 ``check(arguments)`` 理解执行顺序：先读取共享输入，再检查平台入口、Codex
规则与 Claude 权限并汇总诊断。输入不可读取时返回 FAIL；完整检查后发现政策问题时返回 BLOCKED。
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml
from scripts.gates.checks.check_protocol import CheckResult, argument_parser, repository_root

ROOT = repository_root()
CLAUDE_METADATA = ('name', 'description', 'tools', 'model', 'permissionMode')
DOMAIN_HEADINGS = ('## Allowed Scope', '## Forbidden Scope', '## Validation', '## Output Format')
READ_ONLY_AGENTS = {'migration-planner', 'qa-verifier', 'repo-mapper', 'ui-architect'}
WRITE_CAPABLE_AGENTS = {'implementer', 'mhtml-export-specialist', 'openspec-planner'}
ALLOWED_REASONING_EFFORTS = {'low', 'medium', 'high', 'xhigh'}
SKILL_CONTRACT_HEADINGS = ('## 验证门禁', '## 输出格式')


@dataclass(frozen=True)
class RuntimeInputs:
    """保存一次读取后的 runtime 文件内容。"""

    manifest: object
    entries: dict[str, str]
    codex_agents: dict[str, object]
    skills: dict[str, str]
    claude_allowlist: str
    settings: object


def _read_text(path: Path) -> str:
    """按统一编码读取一个 runtime 文本输入。"""
    return path.read_text(encoding='utf-8')


def _load_runtime_inputs(root: Path = ROOT) -> RuntimeInputs:
    """每个共享输入只读取一次；文件不可用直接交给公开入口返回 FAIL。"""

    manifest = yaml.safe_load(_read_text(root / 'harness/agent-runtime.manifest.yaml'))
    agents = manifest.get('domain_agents', {}) if isinstance(manifest, dict) else {}
    entry_paths: set[str] = set()
    skill_paths: set[str] = set()
    if isinstance(agents, dict):
        for config in agents.values():
            if not isinstance(config, dict):
                continue
            skill = config.get('skill')
            if isinstance(skill, str) and skill:
                skill_paths.add(skill)
            entries = config.get('entries', {})
            if isinstance(entries, dict):
                entry_paths.update(
                    value for value in entries.values() if isinstance(value, str) and value
                )
    codex_paths = {str(path.relative_to(root)) for path in (root / '.codex/agents').glob('*.toml')}
    entry_paths.update(codex_paths)
    entries = {relative: _read_text(root / relative) for relative in sorted(entry_paths)}
    codex_agents = {relative: tomllib.loads(entries[relative]) for relative in sorted(codex_paths)}
    return RuntimeInputs(
        manifest=manifest,
        entries=entries,
        codex_agents=codex_agents,
        skills={relative: _read_text(root / relative) for relative in sorted(skill_paths)},
        claude_allowlist=_read_text(root / '.claude/agents/qwen-main-default.md'),
        settings=json.loads(_read_text(root / '.claude/settings.json')),
    )


def _manifest_agents(inputs: RuntimeInputs) -> dict:
    """从已加载 manifest 中返回领域 Agent 映射。"""
    agents = inputs.manifest.get('domain_agents', {}) if isinstance(inputs.manifest, dict) else {}
    return agents if isinstance(agents, dict) else {}


def _check_claude(name: str, relative: str, text: str, skill: str) -> list[str]:
    """检查 Claude 薄入口的元数据、名称和共享 Skill 引用。"""
    if not text.startswith('---\n') or text.count('---') < 2:
        return [f'{relative} missing Claude frontmatter']
    frontmatter, body = text.split('---', 2)[1:]
    errors = [
        f'{relative} missing Claude metadata: {field}'
        for field in CLAUDE_METADATA
        if not re.search(rf'(?m)^{re.escape(field)}:\s*\S', frontmatter)
    ]
    if f'name: {name}' not in frontmatter or skill not in body:
        errors.append(f'{relative} name/Skill entry mismatch')
    if len([line for line in body.splitlines() if line.strip()]) > 4:
        errors.append(f'{relative} copies domain instructions instead of a thin Skill entry')
    return errors


def _check_codex_entry(name: str, relative: str, data: object, skill: str) -> list[str]:
    """检查 Codex 薄入口是否只保存必要元数据与 Skill 跳转。"""
    model = data if isinstance(data, dict) else {}
    errors: list[str] = []
    if model.get('name') != name or len(str(model.get('description') or '').strip()) < 30:
        errors.append(f'{relative} missing Codex name/description metadata')
    instructions = str(model.get('developer_instructions') or '')
    if skill not in instructions:
        errors.append(f'{relative} missing shared Skill entry')
    if len([line for line in instructions.splitlines() if line.strip()]) > 3:
        errors.append(f'{relative} copies domain instructions instead of a thin Skill entry')
    return errors


def _check_qoder(name: str, relative: str, text: str, skill: str) -> list[str]:
    """检查 Qoder 薄入口的名称、使用说明和共享 Skill 引用。"""
    errors: list[str] = []
    if not text.startswith(f'# {name}\n') or '## When To Use' not in text:
        errors.append(f'{relative} missing Qoder name/When To Use metadata')
    if skill not in text or len(text.splitlines()) > 12:
        errors.append(f'{relative} is not a thin shared Skill entry')
    return errors


def _check_agent_entries(inputs: RuntimeInputs | None = None) -> list[str]:
    """按已加载的 manifest 唯一映射验证领域 Agent 薄入口。"""

    current = inputs or _load_runtime_inputs(ROOT)
    agents = _manifest_agents(current)
    if not agents:
        return ['manifest domain_agents is empty']
    errors: list[str] = []
    for name, config in agents.items():
        if not isinstance(config, dict):
            errors.append(f'{name} manifest config must be object')
            continue
        skill = str(config.get('skill') or '')
        if skill not in current.skills:
            errors.append(f'{name} shared Skill missing: {skill}')
        entries = config.get('entries', {})
        for platform in ('claude', 'codex', 'qoder'):
            relative = str(entries.get(platform) or '') if isinstance(entries, dict) else ''
            text = current.entries.get(relative)
            if text is None:
                errors.append(f'{name} {platform} entry missing: {relative}')
                continue
            if platform == 'claude':
                errors.extend(_check_claude(str(name), relative, text, skill))
            elif platform == 'codex':
                errors.extend(
                    _check_codex_entry(
                        str(name), relative, current.codex_agents.get(relative), skill
                    )
                )
            else:
                errors.extend(_check_qoder(str(name), relative, text, skill))
            errors.extend(
                f'{relative} duplicates Skill section: {heading}'
                for heading in DOMAIN_HEADINGS
                if heading in text
            )
    return errors


def _domain_skill(relative: str, agents: dict) -> str | None:
    """查找一个 Codex 领域入口在 manifest 中登记的共享 Skill。"""
    name = Path(relative).stem
    config = agents.get(name, {}) if isinstance(agents, dict) else {}
    entries = config.get('entries', {}) if isinstance(config, dict) else {}
    if not isinstance(entries, dict) or entries.get('codex') != relative:
        return None
    skill = config.get('skill') if isinstance(config, dict) else None
    return skill if isinstance(skill, str) and skill else None


def _check_codex_policy(relative: str, data: object, inputs: RuntimeInputs) -> list[str]:
    """检查一个 Codex Agent 的模型继承、sandbox 与 handoff 边界。"""
    model = data if isinstance(data, dict) else {}
    name = model.get('name')
    description = model.get('description')
    instructions = model.get('developer_instructions')
    agents = _manifest_agents(inputs)
    skill = _domain_skill(relative, agents)
    errors: list[str] = []
    if name != Path(relative).stem:
        errors.append(f'{relative}: name 必须等于文件名 `{Path(relative).stem}`')
    if not isinstance(description, str) or not description.strip():
        errors.append(f'{relative}: description 不能为空')
    if not skill and (not isinstance(instructions, str) or len(instructions.strip()) < 300):
        errors.append(f'{relative}: developer_instructions 过短，无法承载 handoff 和边界契约')
    if 'model' in model:
        errors.append(f'{relative}: 不要固定 model；省略 model 以继承 parent session')
    effort = model.get('model_reasoning_effort')
    if effort is not None and effort not in ALLOWED_REASONING_EFFORTS:
        errors.append(f'{relative}: model_reasoning_effort 非法: {effort}')
    sandbox = model.get('sandbox_mode')
    if name in READ_ONLY_AGENTS and sandbox != 'read-only':
        errors.append(f'{relative}: 只读 agent 必须设置 sandbox_mode = "read-only"')
    if name in WRITE_CAPABLE_AGENTS and sandbox == 'read-only':
        errors.append(f'{relative}: 可写 agent 不得设置 sandbox_mode = "read-only"')
    text = instructions if isinstance(instructions, str) else ''
    if skill:
        if skill not in text:
            errors.append(f'{relative}: developer_instructions 缺少共享 Skill 入口 `{skill}`')
        skill_text = inputs.skills.get(skill, '')
        errors.extend(
            f'{relative}: 共享 Skill 缺少 `{heading}` 契约: {skill}'
            for heading in SKILL_CONTRACT_HEADINGS
            if heading not in skill_text
        )
        for token in ('handoff', 'BLOCKED'):
            if token not in text:
                errors.append(f'{relative}: developer_instructions 缺少 `{token}` 边界契约')
    else:
        for token in ('Handoff', 'BLOCKED', '输出固定为'):
            if token not in text:
                errors.append(f'{relative}: developer_instructions 缺少 `{token}` 契约')
        if (
            name not in {'repo-mapper', 'migration-planner', 'ui-architect'}
            and 'Validation' not in text
        ):
            errors.append(f'{relative}: developer_instructions 缺少 `Validation` 契约')
    return errors


def _check_permission_policy(settings: object) -> list[str]:
    """检查 Claude deny 清单是否覆盖凭据路径和危险命令。"""
    if not isinstance(settings, dict):
        return ['.claude/settings.json 顶层必须是 object']
    permissions = settings.get('permissions', {})
    if not isinstance(permissions, dict):
        return ['.claude/settings.json permissions 必须是 object']
    raw_deny = permissions.get('deny', [])
    if not isinstance(raw_deny, list):
        return ['.claude/settings.json permissions.deny 必须是 array']
    deny = [str(item) for item in raw_deny]
    errors = [
        f'deny 规则中缺少: {required}'
        for required in ('.env', '.mcp.json', '~/.ssh/**', '~/.aws/**', '~/.config/gh/hosts.yml')
        if not any(required in item for item in deny)
    ]
    errors.extend(
        f'deny 规则中缺少危险 Bash 操作: {command}'
        for command in ('git reset --hard', 'git clean -fdx', 'rm -rf /', 'dd if=')
        if not any(command in item for item in deny)
    )
    return errors


def check(arguments: list[str]) -> CheckResult:
    """返回入口对齐、Codex policy 与 Claude permission 的合并结论。"""

    argument_parser(description='检查 Agent runtime policy').parse_args(arguments)
    try:
        inputs = _load_runtime_inputs(ROOT)
    except OSError as exc:
        return CheckResult.execution_failure(
            [f'Agent runtime 输入读取失败: {exc}'], reason='input-unavailable'
        )
    except (yaml.YAMLError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        return CheckResult.from_errors([f'Agent runtime 配置内容无效: {exc}'])
    errors = [
        *_check_agent_entries(inputs),
        *(
            f'Claude main allowlist missing specialist: {name}'
            for name in _manifest_agents(inputs)
            if name not in inputs.claude_allowlist
        ),
        *(
            error
            for relative, data in inputs.codex_agents.items()
            for error in _check_codex_policy(relative, data, inputs)
        ),
        *_check_permission_policy(inputs.settings),
    ]
    return CheckResult.from_errors(errors)
