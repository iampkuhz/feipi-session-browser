#!/usr/bin/env python3
"""提供 create active change 脚本能力。

不负责修改业务代码；由 OpenSpec 命令行或 required Gate 调用。"""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

KEBAB_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')
SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')

PROTECTED_ROOTS = [
    'openspec/',
    'harness/',
    '.claude/',
    '.codex/',
    '.qoder/',
    'CLAUDE.md',
    'AGENTS.md',
]

REQUIRED_GATES = [
    'scripts/openspec/validate_layout.py',
    'scripts/openspec/validate_schema.py',
    'scripts/openspec/validate_active_change.py',
    'scripts/harness/validate_harness_structure.py',
]

TEMPLATE_FILES = {
    'proposal.md': 'proposal.md',
    'design.md': 'design.md',
    'tasks.md': 'tasks.md',
    'specs/spec.md': 'spec.md',
}


def validate_change_id(change_id: str) -> str | None:
    """验证 change id 是否可安全映射为 kebab-case 目录名。"""
    if not change_id:
        return 'change-id is required and cannot be empty'
    if not KEBAB_RE.match(change_id):
        return (
            f"change-id '{change_id}' is not valid kebab-case. "
            'Use only lowercase letters, digits, and hyphens, starting with a letter or digit.'
        )
    if ' ' in change_id or '/' in change_id:
        return f"change-id '{change_id}' must not contain spaces or slashes"
    return None


def _templates_dir(root: Path) -> Path:
    """返回 change skill 的模板目录；缺失时保留预期路径供调用方降级。"""
    candidates = [
        root / '.claude' / 'skills' / 'change' / 'templates',
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]  # 缺失时返回最接近的候选路径，交由调用方报告


def _safe_identity_segment(value: str | None, fallback: str) -> str:
    """把显式 OpenSpec 调用身份限制为安全的单路径段。"""

    cleaned = SAFE_SEGMENT_RE.sub('-', str(value or '').strip()).strip('.-_')
    return (cleaned or fallback)[:80]


def write_file_if_missing(path: Path, content: str, label: str = '') -> bool:
    """仅在目标不存在时写入文件，并返回本次是否创建。

    ``label`` 保留为既有调用契约；文件内容和存在性语义不依赖该展示字段。
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return True


def copy_template_if_missing(
    change_dir: Path,
    dest_rel: str,
    template_name: str,
    templates_dir: Path,
    change_id: str,
) -> bool:
    """从模板创建缺失的 change 文件，并替换 change 占位符。

    模板缺失时仍写入最小标题，确保 scaffold 的幂等文件集合保持完整。
    """
    dest = change_dir / dest_rel
    if dest.exists():
        return False

    tmpl_path = templates_dir / template_name
    content = tmpl_path.read_text(encoding='utf-8') if tmpl_path.exists() else f'# {dest_rel}\n'

    content = content.replace('<change-id>', change_id)
    content = content.replace('<capability>', change_id)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding='utf-8')
    return True


def create_active_change(  # noqa: PLR0912 - idempotent OpenSpec scaffold.
    change_id: str,
    source: str,
    title: str | None = None,
    root: Path | None = None,
    agent_client: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> dict:
    """幂等创建 OpenSpec change 骨架和当前 agent 的 active-change sentinel。

    已存在的 change 文件不会被覆盖；sentinel 会刷新身份字段，但会在复用同一
    change 时保留最初的 ``started_at`` 与 ``source_request``。
    """
    if root is None:
        root = Path.cwd()

    title = title or change_id
    now = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

    raw_session_id = session_id or os.environ.get('FEIPI_SESSION_ID') or ''
    raw_agent_id = agent_id or os.environ.get('FEIPI_AGENT_ID') or ''
    client = _safe_identity_segment(agent_client or os.environ.get('FEIPI_AGENT_CLIENT'), 'unknown')
    change_dir = root / 'openspec' / 'changes' / change_id
    if raw_session_id:
        session_root = (
            root / 'tmp' / 'agent_logs' / client / _safe_identity_segment(raw_session_id, 'unknown')
        )
        agent_dir = (
            session_root / 'agents' / _safe_identity_segment(raw_agent_id, 'agent')
            if raw_agent_id
            else session_root / 'main'
        )
    else:
        agent_dir = root / 'tmp'
    active_change_file = agent_dir / 'active_change.json'

    created: list[str] = []
    existed: list[str] = []
    updated: list[str] = []

    # 先补齐受版本控制的 change 骨架，再处理会话范围的 runtime sentinel。
    if not change_dir.exists():
        change_dir.mkdir(parents=True, exist_ok=True)
        created.append(f'openspec/changes/{change_id}/')
    else:
        existed.append(f'openspec/changes/{change_id}/')

    td = _templates_dir(root)

    for dest_rel, tmpl_name in TEMPLATE_FILES.items():
        ok = copy_template_if_missing(change_dir, dest_rel, tmpl_name, td, change_id)
        if ok:
            created.append(f'openspec/changes/{change_id}/{dest_rel}')
        else:
            existed.append(f'openspec/changes/{change_id}/{dest_rel}')

    if not agent_dir.exists():
        agent_dir.mkdir(parents=True, exist_ok=True)
    else:
        existed.append(str(agent_dir.relative_to(root)) + '/')

    sentinel = {
        'change_id': change_id,
        'change_path': f'openspec/changes/{change_id}/',
        'started_at': now,
        'source_request': source,
        'protected_roots': PROTECTED_ROOTS,
        'required_gates': REQUIRED_GATES,
        'agent_client': client if raw_session_id else '',
        'session_id': raw_session_id,
        'agent_id': raw_agent_id,
    }

    if not active_change_file.exists():
        active_change_file.write_text(json.dumps(sentinel, indent=2) + '\n', encoding='utf-8')
        created.append(str(active_change_file.relative_to(root)))
    else:
        existed.append(str(active_change_file.relative_to(root)))
        try:
            existing = json.loads(active_change_file.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            existing = {}

        if existing.get('change_id') == change_id:
            sentinel['started_at'] = existing.get('started_at') or now
            sentinel['source_request'] = existing.get('source_request') or source
        else:
            updated.append(str(active_change_file.relative_to(root)))

        active_change_file.write_text(json.dumps(sentinel, indent=2) + '\n', encoding='utf-8')

    return {
        'change_id': change_id,
        'created': created,
        'existed': existed,
        'updated': updated,
        'sentinel_path': str(active_change_file),
    }


def build_parser() -> argparse.ArgumentParser:
    """构建公开命令的参数解析器。"""
    parser = argparse.ArgumentParser(
        description='Create an active OpenSpec change and sentinel file.',
    )
    parser.add_argument(
        '--change-id',
        required=True,
        help='Kebab-case change identifier (e.g. my-feature-name).',
    )
    parser.add_argument(
        '--source',
        required=True,
        help="Source of the change request (e.g. 'harness hardening task pack').",
    )
    parser.add_argument(
        '--title',
        default=None,
        help='Optional human-readable title (defaults to change-id).',
    )
    parser.add_argument('--agent-client', default=None, help='Agent client for runtime scope')
    parser.add_argument('--session-id', default=None, help='Session id for runtime scope')
    parser.add_argument('--agent-id', default=None, help='Subagent id for runtime scope')
    return parser


def main() -> int:
    """校验输入、创建 change，并报告 created/existed/updated 分类。"""
    parser = build_parser()
    args = parser.parse_args()

    err = validate_change_id(args.change_id)
    if err:
        print(f'ERROR: {err}', file=sys.stderr)
        return 1

    result = create_active_change(
        change_id=args.change_id,
        source=args.source,
        title=args.title,
        agent_client=args.agent_client,
        session_id=args.session_id,
        agent_id=args.agent_id,
    )

    # 分类输出是调用方确认幂等结果的公开诊断，不合并为模糊的成功消息。
    if result['created']:
        print(f"Created change '{result['change_id']}':")
        for p in result['created']:
            print(f'  + {p}')
    if result['existed']:
        print('Already existed (skipped):')
        for p in result['existed']:
            print(f'    {p}')
    if result['updated']:
        print('Updated active change:')
        for p in result['updated']:
            print(f'  ~ {p}')
    if not result['created'] and not result['updated']:
        print(f"Change '{result['change_id']}' already fully exists — no-op.")

    print(f'\nSentinel: {result["sentinel_path"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
