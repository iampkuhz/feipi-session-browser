"""检查本地 Session 索引的文件、表结构与关键数据完整性。

该检查防止维护命令在缺失、空白或字段损坏的 SQLite 索引上继续工作。唯一入口
``check(arguments)`` 依次执行原有查询并返回有序诊断；诊断表示索引不可可信使用。
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()

# 索引检查是独立维护命令，不依赖已退役的 Python 产品配置。
INDEX_DIR = Path(
    os.environ.get(
        'INDEX_DIR',
        str(Path.home() / '.local' / 'share' / 'feipi' / 'session-browser' / 'local-test-index'),
    )
)
INDEX_PATH = INDEX_DIR / 'index.sqlite'

KNOWN_AGENTS = {'claude_code', 'codex', 'qoder'}

# 每条 Session 记录都必须具备的非空字段。
REQUIRED_NONEMPTY_COLS = [
    'session_key',
    'agent',
    'session_id',
    'project_key',
    'ended_at',
]


@dataclass
class IntegrityResult:
    """汇总各项完整性检查的稳定状态。"""

    checks: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self, name: str) -> None:
        """记录一项通过的检查。"""
        self.checks.append((name, 'PASS'))

    def fail(self, name: str, detail: str = '') -> None:
        """记录一项失败检查及其稳定诊断。"""
        msg = f'{name}: {detail}' if detail else name
        self.errors.append(f'  [FAIL] {msg}')
        self.checks.append((name, 'FAIL'))

    @property
    def all_passed(self) -> bool:
        """仅当所有已执行检查均通过时返回真。"""
        return all(status == 'PASS' for _, status in self.checks)


def _get_connection(db_path: Path) -> sqlite3.Connection | None:
    """打开 SQLite 索引；连接失败时返回 ``None`` 交由入口阻断后续检查。"""
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _check_index_file_exists(result: IntegrityResult) -> None:
    """检查配置的索引文件是否存在。"""
    if INDEX_PATH.is_file():
        result.ok('index file exists')
    else:
        result.fail('index file exists', f'not found at {INDEX_PATH}')


def _check_session_count(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """确认索引至少包含一条 Session 记录，查询失败按失败处理。"""
    try:
        row = conn.execute('SELECT COUNT(*) AS cnt FROM sessions').fetchone()
        cnt = row['cnt']
        if cnt > 0:
            result.ok(f'session count > 0 (total={cnt})')
        else:
            result.fail('session count > 0', 'index is empty')
    except sqlite3.OperationalError as exc:
        result.fail('session count > 0', f'sessions table query failed: {exc}')


def _check_required_fields(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """检查每条 Session 记录的必填字段均非空，查询失败按失败处理。"""
    try:
        # 单次查询收集任一必填字段为空的记录，确保所有字段使用同一判定口径。
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


def _check_no_orphan_agents(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """检查索引中的 Agent 类型均属于已知集合，查询失败按失败处理。"""
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


def _check_scan_log_exists(result: IntegrityResult, conn: sqlite3.Connection) -> None:
    """检查 ``scan_log`` 表；为兼容未初始化 schema，缺表只告警。"""
    try:
        conn.execute('SELECT COUNT(*) FROM scan_log').fetchone()
        result.ok('scan_log table exists')
    except sqlite3.OperationalError:
        # 该表不影响 Session 数据完整性，因此 schema 尚未初始化时保持非阻断。
        result.ok('scan_log table exists (warn-only, missing is acceptable)')


def check(arguments: list[str]) -> CheckResult:
    """解析入口参数并依次执行索引文件与 SQLite 完整性检查。"""
    parser = argument_parser(description='Check local Session index integrity.')
    parser.parse_args(arguments)

    result = IntegrityResult()

    # 文件不存在时数据库检查没有可信输入，直接阻断而不制造后续噪声。
    _check_index_file_exists(result)

    if not INDEX_PATH.is_file():
        return CheckResult.from_errors(result.errors)

    conn = _get_connection(INDEX_PATH)
    if conn is None:
        result.fail('database connection', 'cannot open SQLite connection')
        return CheckResult.from_errors(result.errors)

    try:
        _check_session_count(result, conn)
        _check_required_fields(result, conn)
        _check_no_orphan_agents(result, conn)
        _check_scan_log_exists(result, conn)
    finally:
        conn.close()

    return CheckResult.from_errors(result.errors)
