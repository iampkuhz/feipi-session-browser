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

from scripts.agent_runtime import paths as runtime_paths  # noqa: E402

# 常量定义。

KEBAB_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')

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


# 验证change id。
def validate_change_id(change_id: str) -> str | None:
    """参数：
        change_id: 当前 OpenSpec change id。

    返回：
        None 当 有效；否则 human-读取able validation 错误。
    """
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


# 维护templates 目录。
def _templates_dir(root: Path) -> Path:
    """参数：
        root: 扫描根目录。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    candidates = [
        root / '.claude' / 'skills' / 'change' / 'templates',
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]  # 缺失时返回最接近的候选路径，交由调用方报告


# 写入文件 missing。
def write_file_if_missing(path: Path, content: str, label: str = '') -> bool:
    """参数：
        path: Destination 文件路径。
        content: Text到write 当 文件 is 缺失。
        label: 输出中显示的人类可读标签。

    返回：
        当a 文件 was created; 当 destination al读取y existed.时返回 true。
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return True


# 模板缺失时复制默认结构前先报告失败。
def copy_template_if_missing(
    change_dir: Path,
    dest_rel: str,
    template_name: str,
    templates_dir: Path,
    change_id: str,
) -> bool:
    """参数：
        change_dir: change dir 参数。
        dest_rel: 相对 change 目录的目标路径。
        template_name: openspec/templates 下的 template 文件名。
        templates_dir: OpenSpec template 目录。
        change_id: 当前 OpenSpec change id。

    返回：
        满足条件时返回 true，否则返回 false。
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


# 创建active change。
def create_active_change(  # noqa: PLR0912 - idempotent OpenSpec scaffold.
    change_id: str,
    source: str,
    title: str | None = None,
    root: Path | None = None,
    agent_client: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> dict:
    """参数：
        change_id: 当前 OpenSpec change id。
        source: 输入来源标识。
        title: 可选display title用于generated proposal text。
        root: 扫描根目录。
        agent_client: agent client 参数。
        session_id: 用于筛选记录的 session id。
        agent_id: 用于筛选记录的 agent id。

    返回：
        结果映射。
    """
    if root is None:
        root = Path.cwd()

    title = title or change_id
    now = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

    identity = runtime_paths.identity_from_values(
        agent_client=agent_client,
        session_id=session_id or os.environ.get('FEIPI_SESSION_ID') or '',
        agent_id=agent_id or os.environ.get('FEIPI_AGENT_ID') or '',
    )
    change_dir = root / 'openspec' / 'changes' / change_id
    agent_dir = (
        runtime_paths.agent_log_dir(root, identity) if identity.has_session else root / 'tmp'
    )
    active_change_file = agent_dir / 'active_change.json'

    created: list[str] = []
    existed: list[str] = []
    updated: list[str] = []

    # 创建或复用 change 目录与模板文件。
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

    # tmp/ 目录。
    if not agent_dir.exists():
        agent_dir.mkdir(parents=True, exist_ok=True)
    # 构建parser。
    else:
        existed.append(str(agent_dir.relative_to(root)) + '/')

    sentinel = {
        'change_id': change_id,
        'change_path': f'openspec/changes/{change_id}/',
        'started_at': now,
        'source_request': source,
        'protected_roots': PROTECTED_ROOTS,
        'required_gates': REQUIRED_GATES,
        'agent_client': identity.client if identity.has_session else '',
        'session_id': identity.raw_session_id,
        'agent_id': identity.raw_agent_id,
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


# 构建parser。
def build_parser() -> argparse.ArgumentParser:
    """返回：
    解析后的 HookContext；失败时携带 parse_error。
    """
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


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
    进程退出码。
    """
    parser = build_parser()
    args = parser.parse_args()

    # 校验 change-id。
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

    # 报告输出。
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
