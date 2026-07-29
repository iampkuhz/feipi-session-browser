#!/usr/bin/env python3
"""负责验证跨平台领域 Agent 仅保留平台 metadata 与共享 Skill 入口；不负责修改 Agent；由 Gate 调用。"""

from __future__ import annotations

import re
import sys
import tomllib
from typing import TYPE_CHECKING

import yaml
from scripts.checks._framework import repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
MANIFEST = ROOT / 'harness' / 'agent-runtime.manifest.yaml'
CLAUDE_METADATA = ('name', 'description', 'tools', 'model', 'permissionMode')
DOMAIN_HEADINGS = ('## Allowed Scope', '## Forbidden Scope', '## Validation', '## Output Format')


def _manifest_agents() -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding='utf-8'))
    agents = data.get('domain_agents', {}) if isinstance(data, dict) else {}
    return agents if isinstance(agents, dict) else {}


def _check_claude(name: str, path: Path, skill: str) -> list[str]:
    text = path.read_text(encoding='utf-8')
    errors: list[str] = []
    if not text.startswith('---\n') or text.count('---') < 2:
        return [f'{path.relative_to(ROOT)} missing Claude frontmatter']
    frontmatter, body = text.split('---', 2)[1:]
    for field in CLAUDE_METADATA:
        if not re.search(rf'(?m)^{re.escape(field)}:\s*\S', frontmatter):
            errors.append(f'{path.relative_to(ROOT)} missing Claude metadata: {field}')
    if f'name: {name}' not in frontmatter or skill not in body:
        errors.append(f'{path.relative_to(ROOT)} name/Skill entry mismatch')
    if len([line for line in body.splitlines() if line.strip()]) > 4:
        errors.append(
            f'{path.relative_to(ROOT)} copies domain instructions instead of a thin Skill entry'
        )
    return errors


def _check_codex(name: str, path: Path, skill: str) -> list[str]:
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    errors: list[str] = []
    if data.get('name') != name or len(str(data.get('description') or '').strip()) < 30:
        errors.append(f'{path.relative_to(ROOT)} missing Codex name/description metadata')
    instructions = str(data.get('developer_instructions') or '')
    if skill not in instructions:
        errors.append(f'{path.relative_to(ROOT)} missing shared Skill entry')
    if len([line for line in instructions.splitlines() if line.strip()]) > 3:
        errors.append(
            f'{path.relative_to(ROOT)} copies domain instructions instead of a thin Skill entry'
        )
    return errors


def _check_qoder(name: str, path: Path, skill: str) -> list[str]:
    text = path.read_text(encoding='utf-8')
    errors: list[str] = []
    if not text.startswith(f'# {name}\n') or '## When To Use' not in text:
        errors.append(f'{path.relative_to(ROOT)} missing Qoder name/When To Use metadata')
    if skill not in text or len(text.splitlines()) > 12:
        errors.append(f'{path.relative_to(ROOT)} is not a thin shared Skill entry')
    return errors


def check_agent_entries(platform: str | None = None) -> list[str]:
    """按 manifest 唯一映射验证领域 Agent 薄入口；缺失或解析异常均形成失败诊断。"""
    errors: list[str] = []
    agents = _manifest_agents()
    if not agents:
        return ['manifest domain_agents is empty']
    checkers = {'claude': _check_claude, 'codex': _check_codex, 'qoder': _check_qoder}
    for name, config in agents.items():
        skill = str(config.get('skill') or '')
        entries = config.get('entries', {})
        if not (ROOT / skill).is_file():
            errors.append(f'{name} shared Skill missing: {skill}')
            continue
        for current, checker in checkers.items():
            if platform and current != platform:
                continue
            relative = str(entries.get(current) or '') if isinstance(entries, dict) else ''
            path = ROOT / relative
            if not relative or not path.is_file():
                errors.append(f'{name} {current} entry missing: {relative}')
                continue
            try:
                errors.extend(checker(str(name), path, skill))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                errors.append(f'{relative} parse failed: {exc}')
            text = path.read_text(encoding='utf-8')
            for heading in DOMAIN_HEADINGS:
                if heading in text:
                    errors.append(f'{relative} duplicates Skill section: {heading}')
    return errors


def _check_claude_main_allowlist() -> list[str]:
    text = (ROOT / '.claude/agents/qwen-main-default.md').read_text(encoding='utf-8')
    return [
        f'Claude main allowlist missing specialist: {name}'
        for name in _manifest_agents()
        if name not in text
    ]


def main() -> int:
    """运行跨平台 Agent 入口等价检查，任一入口漂移即返回非零。"""
    errors = [*check_agent_entries(), *_check_claude_main_allowlist()]
    for error in errors:
        print(f'[agentEntryParity] FAIL: {error}', file=sys.stderr)
    if errors:
        return 1
    print(f'[agentEntryParity] PASS: checked {len(_manifest_agents())} domain agents')
    return 0
