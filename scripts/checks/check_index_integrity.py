#!/usr/bin/env python3
"""提供 检查 index integrity 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from scripts.checks._framework import repository_root

REPO_ROOT = repository_root()


REPO_ROOT = repository_root()

# INDEX_PATH 直接定义，不再依赖 session_browser.config
INDEX_DIR = Path(
    os.environ.get(
        'INDEX_DIR',
        str(Path.home() / '.local' / 'share' / 'feipi' / 'session-browser' / 'local-test-index'),
    )
)
INDEX_PATH = INDEX_DIR / 'index.sqlite'

KNOWN_AGENTS = {'claude_code', 'codex', 'qoder'}

# 必需 columns that must 不 be 空用于every session 行。
REQUIRED_NONEMPTY_COLS = [
    'session_key',
    'agent',
    'session_id',
    'project_key',
    'ended_at',
]


@dataclass
class IntegrityResult:
    """汇总 IntegrityResult 的检查结果。

    属性：
        checks: 检查 参数。
    """

    checks: list[tuple[str, str]] = field(default_factory=list)

    # 标记检查通过。
    def ok(self, name: str) -> None:
        """参数：
        name: 稳定的check label shown in gate 输出。
        """
        self.checks.append((name, 'PASS'))

    # 维护fail。
    def fail(self, name: str, detail: str = '') -> None:
        """参数：
        name: 稳定的check label shown in gate 输出。
        detail: detail 参数。
        """
        msg = f'{name}: {detail}' if detail else name
        print(f'  [FAIL] {msg}')
        self.checks.append((name, 'FAIL'))

    # 维护全部 通过。
    @property
    def all_passed(self) -> bool:
        """返回：
        满足条件时返回 true，否则返回 false。
        """
        return all(status == 'PASS' for _, status in self.checks)


# 读取connection。
def _get_connection(db_path: Path) -> sqlite3.Connection | None:
    """参数：
        db_path: 待检查的路径。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


# 检查index 文件 exists。
def check_index_file_exists(result: IntegrityResult) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    """
    if INDEX_PATH.is_file():
        result.ok('index file exists')
    else:
        result.fail('index file exists', f'not found at {INDEX_PATH}')


# 检查session count。
def check_session_count(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    conn: 打开的 SQLite connection。
    """
    try:
        row = conn.execute('SELECT COUNT(*) AS cnt FROM sessions').fetchone()
        cnt = row['cnt']
        if cnt > 0:
            result.ok(f'session count > 0 (total={cnt})')
        else:
            result.fail('session count > 0', 'index is empty')
    except sqlite3.OperationalError as exc:
        result.fail('session count > 0', f'sessions table query failed: {exc}')


# 检查必需 fields。
def check_required_fields(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    conn: 打开的 SQLite connection。
    """
    try:
        # 构建query到find 行 在 any 必需 column is 空。
        clauses = ' OR '.join(f"COALESCE({col}, '') = ''" for col in REQUIRED_NONEMPTY_COLS)
        query = (
            f'SELECT session_key, {", ".join(REQUIRED_NONEMPTY_COLS)} FROM sessions WHERE {clauses}'
        )
        bad_rows = conn.execute(query).fetchall()
        if not bad_rows:
            result.ok('required fields non-empty (all rows)')
        else:
            sample_keys = [r['session_key'] for r in bad_rows[:5]]
            detail = f'{len(bad_rows)} rows have empty required fields; sample: {sample_keys}'
            result.fail('required fields non-empty', detail)
    except sqlite3.OperationalError as exc:
        result.fail('required fields non-empty', f'query failed: {exc}')


# 检查无 orphan agents。
def check_no_orphan_agents(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    conn: 打开SQLite connection queried用于distinct agent 值。
    """
    try:
        row = conn.execute(
            'SELECT DISTINCT agent FROM sessions WHERE agent NOT IN ({})'.format(
                ', '.join('?' for _ in KNOWN_AGENTS)
            ),
            tuple(KNOWN_AGENTS),
        ).fetchall()
        if not row:
            result.ok('no orphan agents')
        else:
            unknown = [r['agent'] for r in row]
            result.fail('no orphan agents', f'unknown agents: {unknown}')
    except sqlite3.OperationalError as exc:
        result.fail('no orphan agents', f'query failed: {exc}')


# 检查扫描 log exists。
def check_scan_log_exists(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """参数：
    result: 用于累积检查结果的可变对象。
    conn: 打开的 SQLite connection。
    """
    try:
        conn.execute('SELECT COUNT(*) FROM scan_log').fetchone()
        result.ok('scan_log table exists')
    except sqlite3.OperationalError:
        # 非阻断：schema 尚未初始化时允许数据表不存在。
        print('  [WARN] scan_log table missing (non-blocking)')
        result.ok('scan_log table exists (warn-only, missing is acceptable)')


# 解析命令行参数并运行脚本入口。


def main() -> int:
    """返回：
    进程退出码。
    """

    print(f'\n{"=" * 60}')
    print('index integrity gate')
    print(f'index path: {INDEX_PATH}')
    print(f'{"=" * 60}\n')

    result = IntegrityResult()

    # 检查1: 文件 exists。
    check_index_file_exists(result)

    if not INDEX_PATH.is_file():
        print('\nIndex file does not exist — cannot run further checks.\n')
        return 1

    conn = _get_connection(INDEX_PATH)
    if conn is None:
        result.fail('database connection', 'cannot open SQLite connection')
        print('\nResult: FAIL\n')
        return 1

    try:
        # 检查2: session count。
        check_session_count(result, conn)

        # 检查3: 必需 fields。
        check_required_fields(result, conn)

        # 检查4: no orphan agents。
        check_no_orphan_agents(result, conn)

        # 检查5: scan_log (warn-仅)。
        check_scan_log_exists(result, conn)
    finally:
        conn.close()

    # 结果汇总。
    passed = sum(1 for _, s in result.checks if s == 'PASS')
    failed = sum(1 for _, s in result.checks if s == 'FAIL')
    total = passed + failed

    print(f'\n{"=" * 60}')
    print(f'summary: {passed}/{total} passed, {failed} failures')
    print(f'{"=" * 60}\n')

    return 0 if result.all_passed else 1
