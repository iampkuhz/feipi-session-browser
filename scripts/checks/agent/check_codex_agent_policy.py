"""检查 Codex custom Agent 配置及其共享 Skill 契约。

一致的 metadata、sandbox 和 handoff 约束可避免子 Agent 越权或丢失验证证据。公开入口是
`check(arguments)`；返回诊断表示 TOML、共享 Skill 或执行边界不符合约定。
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

import yaml
from scripts.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repository_root()
AGENTS_DIR = REPO_ROOT / '.codex' / 'agents'
RUNTIME_MANIFEST = REPO_ROOT / 'harness' / 'agent-runtime.manifest.yaml'

READ_ONLY_AGENTS = {
    'migration-planner',
    'qa-verifier',
    'repo-mapper',
    'ui-architect',
}

WRITE_CAPABLE_AGENTS = {
    'implementer',
    'mhtml-export-specialist',
    'openspec-planner',
}

ALLOWED_REASONING_EFFORTS = {'low', 'medium', 'high', 'xhigh'}
MIN_DEVELOPER_INSTRUCTIONS_CHARS = 300
SKILL_CONTRACT_HEADINGS = ('## 验证门禁', '## 输出格式')


def _load(path: Path) -> dict:
    """解析 Agent TOML；读取或语法错误统一转为带相对路径的 ValueError。"""
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise ValueError(f'{path.relative_to(REPO_ROOT)}: TOML 解析失败: {exc}') from exc


def _domain_skill(path: Path) -> str | None:
    """返回 manifest 为当前 Codex 领域 Agent 指定的共享 Skill。"""
    try:
        data = yaml.safe_load(RUNTIME_MANIFEST.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(
            f'{RUNTIME_MANIFEST.relative_to(REPO_ROOT)}: YAML 解析失败: {exc}'
        ) from exc
    agents = data.get('domain_agents', {}) if isinstance(data, dict) else {}
    config = agents.get(path.stem, {}) if isinstance(agents, dict) else {}
    entries = config.get('entries', {}) if isinstance(config, dict) else {}
    relative = str(entries.get('codex') or '') if isinstance(entries, dict) else ''
    if relative != str(path.relative_to(REPO_ROOT)):
        return None
    skill = str(config.get('skill') or '')
    return skill or None


def _check_skill_entry(rel: Path, instructions: object, skill: str) -> list[str]:
    """验证薄入口及其共享 Skill，避免把领域契约复制回平台配置。"""
    failures: list[str] = []
    text = instructions if isinstance(instructions, str) else ''
    if skill not in text:
        failures.append(f'{rel}: developer_instructions 缺少共享 Skill 入口 `{skill}`')
    for token in ('handoff', 'BLOCKED'):
        if token not in text:
            failures.append(f'{rel}: developer_instructions 缺少 `{token}` 边界契约')

    skill_path = REPO_ROOT / skill
    if not skill_path.is_file():
        failures.append(f'{rel}: 共享 Skill 不存在: {skill}')
        return failures
    skill_text = skill_path.read_text(encoding='utf-8')
    for heading in SKILL_CONTRACT_HEADINGS:
        if heading not in skill_text:
            failures.append(f'{rel}: 共享 Skill 缺少 `{heading}` 契约: {skill}')
    return failures


def _check_agent(path: Path) -> list[str]:
    """检查单个 Codex Agent 的 metadata、执行边界与共享 Skill 入口。"""
    failures: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    data = _load(path)

    name = data.get('name')
    description = data.get('description')
    instructions = data.get('developer_instructions')
    skill = _domain_skill(path)

    if name != path.stem:
        failures.append(f'{rel}: name 必须等于文件名 `{path.stem}`')
    if not isinstance(description, str) or not description.strip():
        failures.append(f'{rel}: description 不能为空')
    if not skill and (
        not isinstance(instructions, str)
        or len(instructions.strip()) < MIN_DEVELOPER_INSTRUCTIONS_CHARS
    ):
        failures.append(f'{rel}: developer_instructions 过短, 无法承载 handoff 和边界契约')

    if 'model' in data:
        failures.append(f'{rel}: 不要固定 model; 省略 model 以继承 parent session')

    effort = data.get('model_reasoning_effort')
    if effort is not None and effort not in ALLOWED_REASONING_EFFORTS:
        failures.append(f'{rel}: model_reasoning_effort 非法: {effort}')

    sandbox = data.get('sandbox_mode')
    if name in READ_ONLY_AGENTS and sandbox != 'read-only':
        failures.append(f'{rel}: 只读 agent 必须设置 sandbox_mode = "read-only"')
    if name in WRITE_CAPABLE_AGENTS and sandbox == 'read-only':
        failures.append(f'{rel}: 可写 agent 不得设置 sandbox_mode = "read-only"')

    if skill:
        failures.extend(_check_skill_entry(rel, instructions, skill))
    else:
        text = instructions or ''
        for token in ('Handoff', 'BLOCKED', '输出固定为'):
            if token not in text:
                failures.append(f'{rel}: developer_instructions 缺少 `{token}` 契约')
        if (
            name not in {'repo-mapper', 'migration-planner', 'ui-architect'}
            and 'Validation' not in text
        ):
            failures.append(f'{rel}: developer_instructions 缺少 `Validation` 契约')

    return failures


def _run_check() -> list[str]:
    """检查全部 Codex Agent；配置目录不存在时保持兼容并返回空结果。"""
    if not AGENTS_DIR.exists():
        return []
    failures: list[str] = []
    for path in sorted(AGENTS_DIR.glob('*.toml')):
        try:
            failures.extend(_check_agent(path))
        except ValueError as exc:
            failures.append(str(exc))
    return failures


def _self_test() -> None:
    assert 'implementer' in WRITE_CAPABLE_AGENTS
    assert 'qa-verifier' in READ_ONLY_AGENTS
    assert 'high' in ALLOWED_REASONING_EFFORTS
    entry = AGENTS_DIR / 'java-backend-implementer.toml'
    assert _domain_skill(entry) == 'skills/authoring/feipi-java-feature-dev/SKILL.md'
    assert not _check_agent(entry)


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回 Codex Agent policy 检查结果。"""
    parser = argument_parser(description='检查 Codex custom agent 配置')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(arguments)

    if args.self_test:
        _self_test()
        return CheckResult()

    return CheckResult.from_errors(_run_check())
