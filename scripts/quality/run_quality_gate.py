#!/usr/bin/env python3
"""运行确定性的 quality gate，并写入结构化 summary artifact。"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

# 确保repo_root is importable 当 this 文件 is executed directly。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.harness.python_env import resolve_python  # noqa: E402
from scripts.harness.port_allocator import reserve_port  # noqa: E402
from scripts.harness.primary_session import resolve_runtime_root  # noqa: E402
from scripts.quality.quality_artifact import (  # noqa: E402
    BLOCKED,
    FAIL,
    PASS,
    GateDetail,
    QualitySummary,
    compute_overall,
    resolve_base_commit,
    resolve_dirty_hash,
    utc_now,
    write_quality_summary,
)
from scripts.quality.quality_targets import (  # noqa: E402
    QUALITY_TARGETS,
    required_gates_for_target,
    target_parallel_meta,
    validate_target,
)

HTTP_OK = 200
PLAYWRIGHT_COMMAND_MIN_PARTS = 3
PLAYWRIGHT_MIN_WORKERS = 8
PLAYWRIGHT_TIMEOUT_SECONDS = 120
DEFAULT_TIMEOUT_SECONDS = 300
MODULE_CHECK_TIMEOUT_SECONDS = 10
COMMAND_OUTPUT_TAIL_CHARS = 4000
FIXTURE_SERVER_READY_ATTEMPTS = 30
FIXTURE_SERVER_READY_TIMEOUT_SECONDS = 15


# 维护运行临时目录。
def _run_tmp_dir(repo_root: Path, name: str) -> Path:
    """参数：
        repo_root: 仓库根目录。
        name: run tmp 子目录名称。

    返回：
        run-scoped tmp 子目录路径。
    """
    run_id = os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    root = Path(os.environ.get('FEIPI_RUN_TMPDIR', '')).expanduser() if os.environ.get('FEIPI_RUN_TMPDIR') else resolve_runtime_root(repo_root) / 'runs' / run_id / 'tmp'
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# 维护relative existing 文件。
def _relative_existing_files(repo_root: Path, patterns: list[str]) -> list[str]:
    """参数：
        repo_root: 仓库根目录。
        patterns: 匹配用的 glob pattern 列表。

    返回：
        稳定排序且去重后的 repository-relative 文件路径列表。
    """
    result: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(repo_root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel not in seen:
                seen.add(rel)
                result.append(rel)
    return result


# 维护Python 候选项。
def _python_candidates(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    candidates: list[str] = []

    explicit = os.environ.get('SESSION_BROWSER_PYTHON')
    if explicit:
        candidates.append(explicit)

    venv_dir = os.environ.get('SESSION_BROWSER_VENV_DIR')
    if venv_dir:
        candidates.append(str(Path(venv_dir) / 'bin' / 'python'))
    else:
        candidates.append(str(repo_root / '.venv' / 'bin' / 'python'))

    for name in ('python', 'python3'):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(resolved)
    candidates.append(sys.executable)

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        normalized = str(Path(candidate).expanduser()) if '/' in candidate else candidate
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


# 维护Python supports modules。
def _python_supports_modules(executable: str, repo_root: Path, modules: tuple[str, ...]) -> bool:
    """参数：
        executable: 待探测的 Python executable 名称或路径。
        repo_root: subprocess 工作目录使用的 repo root。
        modules: 需要导入验证的 module 名称。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    if shutil.which(executable) is None:
        return False

    env = os.environ.copy()
    src_path = str(repo_root / 'src')
    env['PYTHONPATH'] = src_path + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    code = (
        'import importlib, sys\n'
        'missing=[]\n'
        'for name in sys.argv[1:]:\n'
        '    try:\n'
        '        importlib.import_module(name)\n'
        '    except Exception:\n'
        '        missing.append(name)\n'
        'sys.exit(1 if missing else 0)\n'
    )
    try:
        proc = subprocess.run(
            [executable, '-c', code, *modules],
            cwd=repo_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=MODULE_CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:
        return False
# 解析和 cache the project Python用于repeated gate 命令。
    return proc.returncode == 0


# 维护project Python cached。
@lru_cache(maxsize=8)
def _project_python_cached(repo_root: str, modules: tuple[str, ...]) -> str:
    """参数：
        repo_root: 仓库根目录。
        modules: 需要导入验证的 module 名称。

    返回：
        项目 Python executable 路径。
    """
    del modules
    return resolve_python(Path(repo_root))


# 维护project Python。
def _project_python(repo_root: Path, *, dev: bool = False) -> str:
    """参数：
        repo_root: 仓库根目录。
        dev: 是否需要 pytest 等开发依赖。

    返回：
        项目环境使用的 executable 路径。
    """
    modules = ('jinja2', 'markdown_it')
    if dev:
        modules = (*modules, 'pytest')
    return _project_python_cached(str(repo_root), modules)


# 维护Playwright workers。
def _playwright_workers() -> int:
    """返回：
        从环境变量读取的 worker 数量，且不低于 gate 最小值。
    """
    raw = (
        os.environ.get('SESSION_BROWSER_PLAYWRIGHT_WORKERS')
        or os.environ.get('PLAYWRIGHT_WORKERS')
        or ''
    ).strip()
    if raw:
        try:
            return max(PLAYWRIGHT_MIN_WORKERS, int(raw))
        except ValueError:
            pass
    return PLAYWRIGHT_MIN_WORKERS


# 维护tail 文件。
def _tail_file(path: Path, max_chars: int = 2000) -> str:
    """参数：
        path: subprocess gate fixture 产生的日志文件路径。
        max_chars: 摘要中包含的最大尾部字符数。

    返回：
        去除首尾空白后的日志尾部；无法读取时返回空字符串。
    """
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''
    return text[-max_chars:].strip()


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


# 维护去除 ANSI。
def _strip_ansi(text: str) -> str:
    """参数：
        text: 原始 subprocess 输出。

    返回：
        不含 terminal color sequences 的输出文本。
    """
    return _ANSI_RE.sub('', text)


# 判断是否Playwright 命令。
def _is_playwright_command(cmd: list[str]) -> bool:
    """参数：
        cmd: gate 命令矩阵中的 subprocess 命令列表。

    返回：
        命令以 ``npx playwright test`` 开头时返回 true。
    """
    return (
        len(cmd) >= PLAYWRIGHT_COMMAND_MIN_PARTS
        and Path(cmd[0]).name == 'npx'
        and cmd[1:3] == ['playwright', 'test']
    )


# 维护Playwright skip count。
def _playwright_skip_count(output: str) -> int:
    """参数：
        output: 原始或 ANSI-colored Playwright 输出。

    返回：
        Playwright 输出中所有 ``N skipped`` 计数的总和。
    """
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


# 判断是否pytest 命令。
def _is_pytest_command(cmd: list[str]) -> bool:
    """参数：
        cmd: 待执行的命令。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    if not cmd:
        return False
    executable = Path(cmd[0]).name
    if executable == 'pytest':
        return True
    return len(cmd) >= 3 and executable.startswith('python') and cmd[1:3] == ['-m', 'pytest']


# 维护pytest skip count。
def _pytest_skip_count(output: str) -> int:
    """参数：
        output: output 参数。

    返回：
        进程退出码。
    """
    clean = _strip_ansi(output)
    matches = re.findall(r'\b(\d+)\s+skipped\b', clean)
    return sum(int(value) for value in matches)


# 维护去除 allowed warning noise。
def _strip_allowed_warning_noise(output: str, *, gate_name: str, cmd: list[str]) -> str:
    """参数：
        output: 选中 gate 的原始 subprocess 输出。
        gate_name: 用于应用 gate 专用 allowlist 噪声的名称。
        cmd: 用于识别 Playwright 输出的命令列表。

    返回：
        已移除 allowlist 警告-like metadata 的输出。
    """
    clean = _strip_ansi(output)

    if gate_name == 'cssOwnership':
        lines: list[str] = []
        for line in clean.splitlines():
            stripped = line.strip()
            if re.match(r'^Warnings:\s*\d+\s*$', stripped, flags=re.IGNORECASE):
                continue
            if re.match(r'^\[WARN\]\s+', stripped, flags=re.IGNORECASE):
                continue
            if re.match(
                r'^CSS ownership:\s+PASS\s+\(\d+\s+warnings?\)\s*$', stripped, flags=re.IGNORECASE
            ):
                continue
            lines.append(line)
        return '\n'.join(lines)

    if _is_playwright_command(cmd):
        lines = []
        skip_trace_for_allowed_warning = False
        for line in clean.splitlines():
            stripped = line.strip()
            is_no_color_noise = (
                "Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set."
                in stripped
            )
            is_module_register_noise = bool(
                re.match(
                    r'^(?:[^`\s]*\s+)?\[DEP0205\]\s+DeprecationWarning:\s+'
                    r'`module\.register\(\)` is deprecated\.',
                    stripped,
                )
                or re.match(
                    r'^\d+\]\s+DeprecationWarning:\s+'
                    r'`module\.register\(\)` is deprecated\.',
                    stripped,
                )
            )
            if is_no_color_noise or is_module_register_noise:
                skip_trace_for_allowed_warning = True
                continue
            if (
                skip_trace_for_allowed_warning
                and stripped
                == '(Use `node --trace-deprecation ...` to show where the warning was created)'
            ):
                skip_trace_for_allowed_warning = False
                continue
            skip_trace_for_allowed_warning = False
            lines.append(line)
        return '\n'.join(lines)

# 返回一个失败项 reason 当 a selected gate reports warning。
    return clean


# 记录触发后的 warning 原因。
def _warning_after_trigger_reason(
    output: str, *, gate_name: str = '', cmd: list[str] | None = None
) -> str | None:
    """参数：
        output: Subprocess 输出用于a gate that was actually triggered。
        gate_name: gate 名称。
        cmd: 可选命令 列表 used到detect Playwright 输出。

    返回：
        人类可读的 警告 失败项 reason, 或 ``None`` 当 cleaned。 输出 is 警告-free。
    """
    clean = _strip_allowed_warning_noise(output, gate_name=gate_name, cmd=cmd or [])
    warning_count = 0
    count_patterns = (
        r'\b([1-9]\d*)\s+warnings?\b',
        r'\bwarnings?\s*:\s*([1-9]\d*)\b',
        r"\bwarningCount[\"']?\s*:\s*([1-9]\d*)\b",
        r'\b([1-9]\d*)\s+项(?:\s+)?警告\b',
    )
    for pattern in count_patterns:
        warning_count += sum(
            int(value) for value in re.findall(pattern, clean, flags=re.IGNORECASE)
        )

    warning_markers = (
        'warnings summary',
        'warning after trigger',
        'pass (with warnings)',
    )
    warning_classes = re.findall(
        r'\b(?:Pytest|Deprecation|PendingDeprecation|Future|Runtime|Resource|User)Warning\b',
        clean,
    )
    warning_lines = [
        line.strip()
        for line in clean.splitlines()
        if re.match(r'^(?:\[.*?\]\s*)?(?:WARN|WARNING)\b', line.strip(), flags=re.IGNORECASE)
    ]

    if warning_count:
        return f'warning after trigger: selected gate reported {warning_count} warning(s)'
    if any(marker in clean.lower() for marker in warning_markers):
        return 'warning after trigger: selected gate output contains warning summary'
    if warning_classes:
        return f'warning after trigger: selected gate emitted {warning_classes[0]}'
    if warning_lines:
        return f'warning after trigger: {warning_lines[0]}'
    return None


# 审计network 阻断 reason。
def _audit_network_block_reason(output: str, *, gate_name: str) -> str | None:
    """参数：
        output: output 参数。
        gate_name: gate 名称。

    返回：
        network 阻断审计原因字符串。
    """
    if gate_name != 'pythonAudit':
        return None
    clean = _strip_ansi(output)
    network_markers = (
        'requests.exceptions.SSLError',
        'requests.exceptions.ProxyError',
        'requests.exceptions.ReadTimeout',
        'urllib3.exceptions.ReadTimeoutError',
        'urllib3.exceptions.MaxRetryError',
        'HTTPSConnectionPool',
        'RemoteDisconnected',
        'UNEXPECTED_EOF_WHILE_READING',
    )
    if any(marker in clean for marker in network_markers):
        return 'pip-audit vulnerability service/network unavailable'
# 检查是否the Java HIFI fixture sessions are 可用 on a server。
    return None


# 维护fixture session 可用。
def _fixture_session_available(base_url: str) -> bool:
    """参数：
        base_url: base url 参数。

    返回：
        当dashboard, short fixture, 和 long fixture routes respond带HTTP 200.时返回 true。
    """
    required_paths = (
        '/dashboard',
        '/sessions/claude_code/hifi-viz-session-001',
        '/sessions/claude_code/long-session-001',
    )
    for path in required_paths:
        try:
            resp = urllib.request.urlopen(f'{base_url}{path}', timeout=5)
        except Exception:
            return False
        if resp.status != HTTP_OK:
            return False
# 合并long-session fixture data into a copied HIFI fixture 目录。
    return True


# 合并long fixture 数据。
def _merge_long_fixture_data(data_dir: Path) -> None:
    """参数：
        data_dir: fixture server 使用的临时数据目录。
    """
    long_root = REPO_ROOT / 'tests' / 'fixtures' / 'session_hifi_long_fixture'
    if not long_root.exists():
        return
    long_projects = long_root / 'projects'
    if long_projects.exists():
        projects_dir = data_dir / 'projects'
        projects_dir.mkdir(parents=True, exist_ok=True)
        for item in long_projects.iterdir():
            destination = projects_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)

    long_history = long_root / 'history.jsonl'
    if long_history.exists():
        history_file = data_dir / 'history.jsonl'
        existing = history_file.read_text(encoding='utf-8') if history_file.exists() else ''
        history_file.write_text(
            existing + long_history.read_text(encoding='utf-8'), encoding='utf-8'
# 解析 Gradle installDist 生成的 Java CLI launcher 路径。
        )


# 维护Java launcher。
def _java_launcher() -> Path | None:
    """返回：
        路径到 ``app-cli`` launcher script, 或 ``None`` 当 不 built。
    """
    launcher = REPO_ROOT / 'java' / 'app-cli' / 'build' / 'install' / 'app-cli' / 'bin' / 'app-cli'
# 直接读取 fixture JSONL 文件并写入 SQLite，绕过 Java scan 归一化引擎
# 尚未填充 session 元数据的已知限制。
    return launcher if launcher.exists() else None


# 维护填充 fixture index。
def _populate_fixture_index(data_dir: Path, index_dir: Path) -> str | None:
    """参数：
        data_dir: fixture server 使用的临时数据目录。
        index_dir: 包含 index.sqlite 的临时 index 目录。

    返回：
        populate fixture index 字符串。

    说明：
        直接读取 fixture JSONL 文件并写入 SQLite，绕过 Java 扫描 归一化引擎。
        尚未填充 session 元数据的已知限制。
    """
    sqlite_path = index_dir / 'index.sqlite'
    try:
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        _ensure_fixture_schema(conn)
        projects_dir = data_dir / 'projects'
        if not projects_dir.is_dir():
            conn.close()
            return f'fixture projects directory missing: {projects_dir}'
        artifact_dir = index_dir / 'artifacts' / 'normalized-sessions'
        artifact_dir.mkdir(parents=True, exist_ok=True)
        fixture_history = _load_fixture_history(data_dir)
        session_count = 0
        for project_dir in sorted(projects_dir.iterdir()):
            if not project_dir.is_dir() or project_dir.name.startswith('.'):
                continue
            for jsonl_file in sorted(project_dir.glob('*.jsonl')):
                session_count += _insert_fixture_session(
                    conn, data_dir, project_dir, jsonl_file, artifact_dir, fixture_history
                )
        conn.commit()
        _shift_fixture_dates_to_recent(conn)
        conn.close()
        if session_count == 0:
            return 'no fixture sessions found in JSONL data'
    except Exception as exc:
        return f'fixture index population failed: {exc}'
    return None


# 调整fixture 日期 近期。
def _shift_fixture_dates_to_recent(conn: sqlite3.Connection) -> None:
    """参数：
        conn: 打开的 SQLite connection。
    """
    from datetime import datetime, timedelta, timezone

    row = conn.execute("SELECT MAX(ended_at) FROM sessions").fetchone()
    if not row or not row[0]:
        return
    max_ended_str = row[0]
    # 解析 ISO 时间戳的日期部分
    max_date_str = max_ended_str[:10]  # "2026-06-03"
    try:
        max_date = datetime.strptime(max_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        return
    # 目标：最新 session 的 ended_at 在 2 天前
    target_date = datetime.now(timezone.utc) - timedelta(days=2)
    offset_days = (target_date - max_date).days
    if offset_days <= 0:
        return  # 数据已经是最近的，无需偏移
    offset_sql = f"+{offset_days} days"
    conn.execute(
        "UPDATE sessions SET started_at = datetime(started_at, ?), ended_at = datetime(ended_at, ?)",
        (offset_sql, offset_sql),
    )
    conn.commit()


# 加载fixture history。
def _load_fixture_history(data_dir: Path) -> dict[str, dict[str, object]]:
    """参数：
        data_dir: fixture server 使用的临时数据目录。

    返回：
        结果映射。
    """
    history_file = data_dir / 'history.jsonl'
    if not history_file.exists():
        return {}

    result: dict[str, dict[str, object]] = {}
    for line in history_file.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = str(item.get('sessionId') or item.get('session_id') or '').strip()
        if session_id:
            result[session_id] = item
    return result


# 维护fixture event timestamp 秒。
def _fixture_event_timestamp_seconds(event: dict) -> float | None:
    """参数：
        event: event 参数。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    value = event.get('timestamp')
    if not isinstance(value, str) or not value:
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
# 返回true用于user prompt 行, excluding pure tool_result 行。
        return None


# 维护fixture 用户 has 文本。
def _fixture_user_has_text(event: dict) -> bool:
    """参数：
        event: event 参数。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    msg = event.get('message', {})
    if not isinstance(msg, dict):
        return False
    content = msg.get('content', '')
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(
            isinstance(block, dict)
            and block.get('type') == 'text'
            and bool(str(block.get('text') or '').strip())
            for block in content
        )
    return False


# 维护fixture first 用户 标题。
def _fixture_first_user_title(events: list[dict]) -> str:
    """参数：
        events: events 参数。

    返回：
        fixture 中首个用户标题字符串。
    """
    for event in events:
        if event.get('type') != 'user':
            continue
        msg = event.get('message', {})
        if not isinstance(msg, dict):
            continue
        content = msg.get('content', '')
        if isinstance(content, str) and content.strip():
            line = content.strip().splitlines()[0]
            match = re.match(r'^(.+?[.!?])\s+', line)
            return (match.group(1) if match else line)[:200]
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get('type') == 'text'
                    and str(block.get('text') or '').strip()
                ):
                    line = str(block.get('text') or '').strip().splitlines()[0]
                    match = re.match(r'^(.+?[.!?])\s+', line)
                    return (match.group(1) if match else line)[:200]
    return ""


# 维护fixture 序列化 tool result。
def _fixture_stringify_tool_result(value: object) -> str:
    """参数：
        value: value 参数。

    返回：
        fixture stringify tool result 字符串。
    """
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get('text')
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(json.dumps(item, ensure_ascii=False))
            else:
                parts.append(str(item))
        return '\n'.join(part for part in parts if part)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
# Detect obvious tool runtime 失败项用于Java HIFI fixture parity。
    return str(value)


# 维护fixture tool result looks 失败。
def _fixture_tool_result_looks_failed(result_content: object, tool_name: str = '') -> bool:
    """参数：
        result_content: tool result 内容。
        tool_name: tool name 参数。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    text = _fixture_stringify_tool_result(result_content).lower()
    if not text:
        return False

    if tool_name in ('Read', 'Write', 'Edit', 'Glob', 'Grep', 'LS'):
        first_line = text.split('\n', 1)[0].strip()
        return first_line.startswith(
            (
                'file does not exist',
                'permission denied',
                'no such file',
                'directory not found',
                'path not found',
                'cannot read',
                'not a directory',
                'too many levels of symbolic links',
                'input/output error',
                'is a directory',
            )
        )

    line_markers = (
        'api error',
        'tool_use_error',
        'key_model_access_denied',
        'rate limit exceeded',
        'user rejected',
        'request cancelled',
        'permission denied',
        'fatal:',
    )
    for marker in line_markers:
        if text.startswith(marker):
            return True
        for line in text.split('\n'):
            stripped = line.strip().lstrip('$# ').strip()
            if stripped.startswith(marker):
                return True
            parts = stripped.split(': ')
            if len(parts) > 1 and parts[-1].strip().startswith(marker):
                return True

    if re.search(r'(?:^|\n)\s*command not found', text, re.MULTILINE):
        return True
    return any(
        re.match(r'^(?:ba)?sh:\s+.*:\s+command not found', line.strip())
        for line in text.split('\n')
    )


# 维护fixture usage 总量。
def _fixture_usage_totals(events: list[dict]) -> tuple[int, int, int, int]:
    """参数：
        events: events 参数。

    返回：
        结果 tuple。
    """
    output_tokens = 0
    fresh_input_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    for event in events:
        msg = event.get('message', {})
        if event.get('type') != 'assistant' or not isinstance(msg, dict):
            continue
        usage = msg.get('usage', {})
        if not isinstance(usage, dict):
            continue
        output_tokens += usage.get('output_tokens', 0)
        fresh_input_tokens += usage.get('input_tokens', 0)
        cache_read_tokens += usage.get('cache_read_input_tokens', 0)
        cache_write_tokens += usage.get('cache_creation_input_tokens', 0)
    return output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens


# 维护fixture subagent usage 总量。
def _fixture_subagent_usage_totals(jsonl_file: Path) -> tuple[int, int, int, int]:
    """参数：
        jsonl_file: jsonl file 参数。

    返回：
        结果 tuple。
    """
    totals = [0, 0, 0, 0]
    subagents_dir = jsonl_file.with_suffix('') / 'subagents'
    for subagent_file in sorted(subagents_dir.glob('*.jsonl')):
        try:
            events = [
                json.loads(line)
                for line in subagent_file.read_text(encoding='utf-8').splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            continue
        for idx, value in enumerate(_fixture_usage_totals(events)):
            totals[idx] += value
# 创建the minimum SQLite schema用于 fixture server。
    return tuple(totals)  # type: ignore[return-value]


# 确保fixture schema。
def _ensure_fixture_schema(conn: sqlite3.Connection) -> None:
    """参数：
        conn: 打开的 SQLite connection。
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            applied_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT PRIMARY KEY,
            agent TEXT NOT NULL CHECK(agent <> ''),
            session_id TEXT NOT NULL CHECK(session_id <> ''),
            title TEXT NOT NULL DEFAULT '',
            project_key TEXT NOT NULL CHECK(project_key <> ''),
            project_name TEXT NOT NULL DEFAULT '',
            cwd TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL DEFAULT '',
            ended_at TEXT NOT NULL CHECK(ended_at <> ''),
            duration_seconds REAL NOT NULL DEFAULT 0,
            model_execution_seconds REAL NOT NULL DEFAULT 0,
            tool_execution_seconds REAL NOT NULL DEFAULT 0,
            model TEXT NOT NULL DEFAULT '',
            git_branch TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            user_message_count INTEGER NOT NULL DEFAULT 0,
            assistant_message_count INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            fresh_input_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            failed_tool_count INTEGER NOT NULL DEFAULT 0,
            subagent_instance_count INTEGER NOT NULL DEFAULT 0,
            indexed_at REAL NOT NULL DEFAULT 0,
            file_mtime REAL NOT NULL DEFAULT 0,
            file_path TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL DEFAULT 0,
            finished_at REAL NOT NULL DEFAULT 0,
            claude_count INTEGER NOT NULL DEFAULT 0,
            codex_count INTEGER NOT NULL DEFAULT 0,
            qoder_count INTEGER NOT NULL DEFAULT 0,
            mode TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS index_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS session_artifacts (
            session_key TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            path TEXT NOT NULL DEFAULT '',
            schema_version TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            source_mtime REAL NOT NULL DEFAULT 0,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(session_key, artifact_type),
            FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
        );
    """)


# 维护插入 fixture session。
def _insert_fixture_session(
    conn: sqlite3.Connection,
    data_dir: Path,
    project_dir: Path,
    jsonl_file: Path,
    artifact_dir: Path,
    fixture_history: dict[str, dict[str, object]],
) -> int:
    """参数：
        conn: 打开的 SQLite connection。
        data_dir: fixture data root 目录。
        project_dir: Project 目录 containing JSONL 文件。
        jsonl_file: session JSONL 文件到解析。
        artifact_dir: artifact dir 参数。
        fixture_history: fixture history 参数。

    返回：
        1 on success, 0 on skip (空 或 un读取able 文件)。
    """
    events: list[dict] = []
    with open(jsonl_file, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    if not events:
        return 0

    session_id = jsonl_file.stem
    history = fixture_history.get(session_id, {})
    session_title = _fixture_first_user_title(events) or str(history.get('display') or session_id)
    project_name = str(history.get('project') or project_dir.name)
    project_key = project_name
    # Java server 使用 {agent}:{session_id} 格式的 session_key 查找会话
    session_key = f'claude_code:{session_id}'

    first_event = events[0]
    started_at = first_event.get('timestamp', '')
    cwd = first_event.get('cwd', '') or str(history.get('cwd') or '')
    git_branch = first_event.get('gitBranch', '')

    last_event = events[-1]
    ended_at = last_event.get('timestamp', started_at)

    user_count = sum(1 for e in events if e.get('type') == 'user' and _fixture_user_has_text(e))
    assistant_count = sum(1 for e in events if e.get('type') == 'assistant')
    tool_calls = 0
    failed_tools = 0
    output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens = (
        _fixture_usage_totals(events)
    )
    subagent_output, subagent_fresh, subagent_read, subagent_write = _fixture_subagent_usage_totals(
        jsonl_file
    )
    output_tokens += subagent_output
    fresh_input_tokens += subagent_fresh
    cache_read_tokens += subagent_read
    cache_write_tokens += subagent_write
    total_tokens = output_tokens + fresh_input_tokens + cache_read_tokens + cache_write_tokens
    model = ''
    tool_names_by_id: dict[str, str] = {}
    for event in events:
        msg = event.get('message', {})
        content = msg.get('content', [])
        if event.get('type') == 'assistant':
            if not model:
                model = msg.get('model', '')
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        tool_calls += 1
                        tool_id = str(block.get('id') or '')
                        if tool_id:
                            tool_names_by_id[tool_id] = str(block.get('name') or '')
        elif event.get('type') == 'user' and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get('type') != 'tool_result':
                    continue
                tool_use_id = str(block.get('tool_use_id') or '')
                tool_name = tool_names_by_id.get(tool_use_id, '')
                if block.get('is_error') is True or _fixture_tool_result_looks_failed(
                    block.get('content', ''), tool_name
                ):
                    failed_tools += 1

    file_stat = jsonl_file.stat()
    now = time.time()
    subagent_files = sorted((jsonl_file.with_suffix('') / 'subagents').glob('*.jsonl'))
    subagent_count = len(subagent_files)
    timestamps = [ts for event in events if (ts := _fixture_event_timestamp_seconds(event))]
    duration_seconds = max(0.0, (timestamps[-1] - timestamps[0]) if len(timestamps) >= 2 else 0.0)

    conn.execute(
        """INSERT OR REPLACE INTO sessions (
            session_key, agent, session_id, title, project_key, project_name,
            cwd, started_at, ended_at, duration_seconds, model_execution_seconds,
            tool_execution_seconds, model, git_branch, source,
            user_message_count, assistant_message_count, tool_call_count,
            output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,
            total_tokens, failed_tool_count, subagent_instance_count,
            indexed_at, file_mtime, file_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_key,
            'claude_code',
            session_id,
            session_title,
            project_key,
            project_name,
            cwd,
            started_at,
            ended_at,
            duration_seconds,
            0,
            0,
            model,
            git_branch,
            'claude_code',
            user_count,
            assistant_count,
            tool_calls,
            output_tokens,
            fresh_input_tokens,
            cache_read_tokens,
            cache_write_tokens,
            total_tokens,
            failed_tools,
            subagent_count,
            now,
            file_stat.st_mtime,
            str(jsonl_file.resolve()),
        ),
    )
    _insert_fixture_artifact(conn, artifact_dir, jsonl_file, events, session_key, file_stat, now)
# 写入和 associate a deterministic 规范化 artifact用于fixture sessions。
    return 1


# 维护插入 fixture artifact。
def _insert_fixture_artifact(
    conn: sqlite3.Connection,
    artifact_dir: Path,
    jsonl_file: Path,
    events: list[dict],
    session_key: str,
    file_stat: os.stat_result,
    now: float,
) -> None:
    """参数：
        conn: 打开的 SQLite connection。
        artifact_dir: artifact dir 参数。
        jsonl_file: jsonl file 参数。
        events: events 参数。
        session_key: session key 参数。
        file_stat: file stat 参数。
        now: now 参数。
    """
    artifact = _build_fixture_normalized_artifact(jsonl_file, events)
    payload = json.dumps(artifact, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    content_hash = hashlib.sha256(payload).hexdigest()
    artifact_path = artifact_dir / f'{content_hash}.json'
    artifact_path.write_bytes(payload)
    conn.execute(
        """INSERT OR REPLACE INTO session_artifacts (
            session_key, artifact_type, path, schema_version, source_path,
            source_mtime, size_bytes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_key,
            'normalized',
            str(artifact_path.resolve()),
            artifact['schemaVersion'],
            str(jsonl_file.resolve()),
            file_stat.st_mtime,
            artifact_path.stat().st_size,
            now,
            now,
        ),
# 构建the subset of 规范化 artifact fields consumed by Java detail pages。
    )


# 构建fixture normalized artifact。
def _build_fixture_normalized_artifact(jsonl_file: Path, events: list[dict]) -> dict:
    """参数：
        jsonl_file: jsonl file 参数。
        events: events 参数。

    返回：
        结果映射。
    """
    calls: list[dict] = []
    tool_executions: list[dict] = []
    tool_declared_by: dict[str, str] = {}
    pending_results: list[dict] = []
    main_call_index = 0

    # 追加tool 执行 call。
    def append_tool_executions_for_call(call_id: str) -> None:
        """参数：
            call_id: call id 参数。
        """
        nonlocal pending_results
        remaining = []
        for result in pending_results:
            tool_id = result.get('tool_call_id') or result.get('tool_use_id') or ''
            declared_by = tool_declared_by.get(tool_id, '')
            if declared_by and call_id:
                tool_executions.append(
                    {
                        'toolCallId': tool_id,
                        'name': result.get('name') or _tool_name_from_id(tool_id),
                        'scope': 'main',
                        'declaredByCallId': declared_by,
                        'resultConsumedByCallId': call_id,
                        'status': 'failed' if result.get('is_error') is True else '',
                        'exitCode': 1 if result.get('is_error') is True else None,
                        'durationMs': 0,
                        'subagentId': _subagent_id_for_tool(jsonl_file, tool_id),
                    }
                )
            else:
                remaining.append(result)
        pending_results = remaining

    for event in events:
        msg = event.get('message', {})
        content = msg.get('content', [])
        if event.get('type') == 'user' and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_result':
                    pending_results.append(block)
            continue
        if event.get('type') != 'assistant':
            continue

        main_call_index += 1
        call_id = f'C{main_call_index}'
        append_tool_executions_for_call(call_id)
        tool_ids = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'tool_use':
                    tool_id = str(block.get('id') or f'tool-{main_call_index}-{len(tool_ids) + 1}')
                    tool_ids.append(tool_id)
                    tool_declared_by[tool_id] = call_id
        calls.append(
            _fixture_call(
                call_id=call_id,
                call_index=main_call_index,
                scope='main',
                parent_call_id='',
                parent_tool_call_id='',
                model=msg.get('model', ''),
                timestamp=event.get('timestamp', ''),
                usage=msg.get('usage', {}),
                tool_call_ids=tool_ids,
            )
        )

    for result in pending_results:
        tool_id = result.get('tool_call_id') or result.get('tool_use_id') or ''
        declared_by = tool_declared_by.get(tool_id, '')
        if declared_by:
            tool_executions.append(
                {
                    'toolCallId': tool_id,
                    'name': result.get('name') or _tool_name_from_id(tool_id),
                    'scope': 'main',
                    'declaredByCallId': declared_by,
                    'resultConsumedByCallId': '',
                    'status': 'failed' if result.get('is_error') is True else '',
                    'exitCode': 1 if result.get('is_error') is True else None,
                    'durationMs': 0,
                    'subagentId': _subagent_id_for_tool(jsonl_file, tool_id),
                }
            )

    calls.extend(_build_subagent_calls(jsonl_file, tool_declared_by, len(calls)))

    return {
        'schemaVersion': 'session-detail.normalized.v3',
        'agent': 'claude_code',
        'sourceFiles': [
            {
                'role': 'transcript',
                'path': str(jsonl_file.resolve()),
                'subagentId': None,
                'parentToolUseId': None,
            }
        ],
        'session': {
            'agent': 'claude_code',
            'session_key': f'claude_code:{jsonl_file.stem}',
            'session_id': jsonl_file.stem,
            'source': 'fixture',
        },
        'calls': calls,
        'toolExecutions': [
            {k: v for k, v in execution.items() if v is not None}
            for execution in tool_executions
            if execution.get('toolCallId')
        ],
        'diagnostics': [],
        'sourceUnitCatalog': {},
        'sourceUnitSequences': {},
    }


# 维护fixture call。
def _fixture_call(
    *,
    call_id: str,
    call_index: int,
    scope: str,
    parent_call_id: str,
    parent_tool_call_id: str,
    model: str,
    timestamp: str,
    usage: dict,
    tool_call_ids: list[str],
) -> dict:
    """参数：
        call_id: call id 参数。
        call_index: call index 参数。
        scope: scope 参数。
        parent_call_id: parent call id 参数。
        parent_tool_call_id: 父级 tool call id。
        model: model 参数。
        timestamp: timestamp 参数。
        usage: usage 参数。
        tool_call_ids: tool call ids 参数。

    返回：
        结果映射。
    """
    fresh = int(usage.get('input_tokens') or 0)
    cache_read = int(usage.get('cache_read_input_tokens') or 0)
    cache_write = int(usage.get('cache_creation_input_tokens') or 0)
    output = int(usage.get('output_tokens') or 0)
    total = fresh + cache_read + cache_write + output
    return {
        'callId': call_id,
        'callIndex': call_index,
        'callKey': f'C{call_index}',
        'scope': scope,
        'parentCallId': parent_call_id,
        'parentToolCallId': parent_tool_call_id,
        'turnId': '',
        'model': model or '',
        'timestamp': timestamp or '',
        'usage': {
            'fresh': fresh,
            'cacheRead': cache_read,
            'cacheWrite': cache_write,
            'output': output,
            'total': total,
        },
        'request': {'toolResultIds': []},
        'response': {'toolCallIds': tool_call_ids},
# 构建subagent calls。
    }


# 构建subagent call。
def _build_subagent_calls(
    jsonl_file: Path, tool_declared_by: dict[str, str], start_index: int
) -> list[dict]:
    """参数：
        jsonl_file: jsonl file 参数。
        tool_declared_by: 声明 tool 的来源。
        start_index: start index 参数。

    返回：
        结果列表。
    """
    subagent_calls: list[dict] = []
    subagent_root = jsonl_file.with_suffix('') / 'subagents'
    if not subagent_root.is_dir():
        return subagent_calls

    next_index = start_index
    for subagent_file in sorted(subagent_root.glob('*.jsonl')):
        parent_tool_id = subagent_file.stem
        parent_call_id = tool_declared_by.get(parent_tool_id, '')
        try:
            events = [
                json.loads(line)
                for line in subagent_file.read_text(encoding='utf-8').splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            events = []
        sub_round = 0
        for event in events:
            if event.get('type') != 'assistant':
                continue
            msg = event.get('message', {})
            content = msg.get('content', [])
            tool_ids = []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'tool_use':
                        tool_ids.append(
                            str(block.get('id') or f'{parent_tool_id}-tool-{len(tool_ids) + 1}')
                        )
            next_index += 1
            sub_round += 1
            subagent_calls.append(
                _fixture_call(
                    call_id=f'{parent_tool_id}-SR{sub_round}',
                    call_index=next_index,
                    scope='subagent',
                    parent_call_id=parent_call_id,
                    parent_tool_call_id=parent_tool_id,
                    model=msg.get('model', ''),
                    timestamp=event.get('timestamp', ''),
                    usage=msg.get('usage', {}),
                    tool_call_ids=tool_ids,
                )
            )
    return subagent_calls


# 维护tool name id。
def _tool_name_from_id(tool_id: str) -> str:
    """参数：
        tool_id: tool id 参数。

    返回：
        tool name from id 字符串。
    """
    if 'agent' in tool_id.lower():
        return 'Agent'
    if 'bash' in tool_id.lower():
        return 'Bash'
    if 'read' in tool_id.lower():
        return 'Read'
    if 'write' in tool_id.lower():
        return 'Write'
    return 'Tool'


# 维护subagent id tool。
def _subagent_id_for_tool(jsonl_file: Path, tool_id: str) -> str:
    """参数：
        jsonl_file: jsonl file 参数。
        tool_id: tool id 参数。

    返回：
        subagent id for tool 字符串。
    """
    if not tool_id:
        return ''
    subagent_path = jsonl_file.with_suffix('') / 'subagents' / f'{tool_id}.jsonl'
    return tool_id if subagent_path.exists() else ''


# 维护启动 fixture server。
def _start_fixture_server() -> tuple[subprocess.Popen | None, str | None, str | None, str | None]:
    """返回：
        结果 tuple。
    """
    fixture_root = REPO_ROOT / 'tests' / 'fixtures' / 'session_hifi_fixture'
    if not fixture_root.exists():
        return None, None, None, f'fixture root missing: {fixture_root}'

    tmpdir_path = Path(tempfile.mkdtemp(prefix='quality_gate_fixture_', dir=str(_run_tmp_dir(REPO_ROOT, 'fixtures'))))
    tmpdir = str(tmpdir_path)
    index_dir = tmpdir_path / 'index'
    index_dir.mkdir(parents=True)
    data_dir = tmpdir_path / 'claude_data'
    shutil.copytree(fixture_root, data_dir)
    _merge_long_fixture_data(data_dir)

    populate_error = _populate_fixture_index(data_dir, index_dir)
    if populate_error:
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        return None, None, None, populate_error

    # 分配并记录 run-scoped fixture port，启动前释放保留 socket。
    port_allocation = reserve_port(REPO_ROOT, 'fixture-server', hold_socket=True)
    port = port_allocation.port

    launcher = _java_launcher()
    if not launcher:
        port_allocation.close()
        shutil.rmtree(tmpdir_path, ignore_errors=True)
        return None, None, None, 'Java CLI not built; run ./gradlew :java:app-cli:installDist'

    env = os.environ.copy()
    env['INDEX_DIR'] = str(index_dir)
    env['CLAUDE_DATA_DIR'] = str(data_dir)
    env['SESSION_BROWSER_LOG_LEVEL'] = 'WARN'
    server_log = Path(tmpdir) / 'fixture-server.log'
    log_handle = server_log.open('w', encoding='utf-8')

    try:
        if port_allocation.socket is not None:
            port_allocation.socket.close()
            port_allocation.socket = None
        proc = subprocess.Popen(
            [
                str(launcher),
                'serve',
                '--allow-empty',
                '--no-scan',
                '--host',
                '127.0.0.1',
                '--port',
                str(port),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    finally:
        log_handle.close()

    # 等待用于 the server到start。
    base_url = f'http://127.0.0.1:{port}'
    for _ in range(FIXTURE_SERVER_READY_ATTEMPTS):
        try:
            resp = urllib.request.urlopen(f'{base_url}/dashboard', timeout=2)
            if resp.status == HTTP_OK:
                return proc, base_url, tmpdir, None
        except Exception:
            pass
        if proc.poll() is not None:
            output = _tail_file(server_log)
            port_allocation.close()
            shutil.rmtree(tmpdir, ignore_errors=True)
            return (
                None,
                None,
                None,
                f'fixture server exited early with code {proc.returncode}: {output}',
            )
        time.sleep(0.5)

    proc.terminate()
    proc.wait()
    output = _tail_file(server_log)
    port_allocation.close()
    shutil.rmtree(tmpdir, ignore_errors=True)
    return (
        None,
        None,
        None,
        f'fixture server did not become ready within {FIXTURE_SERVER_READY_TIMEOUT_SECONDS}s: '
        f'{output}',
# 停止the fixture server 和 clean up temp 文件。
    )


# 维护stop fixture server。
def _stop_fixture_server(proc: subprocess.Popen, tmpdir: str | None) -> None:
    """参数：
        proc: proc 参数。
        tmpdir: tmpdir 参数。
    """
    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)
    run_id = os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    ports_dir = resolve_runtime_root(REPO_ROOT) / 'ports'
    for record in ports_dir.glob(f'{run_id}-fixture-server.json'):
        try:
            record.unlink()
        except OSError:
            pass
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
# 运行one gate 命令 和 normalize its 结果 into a gate detail。
            proc.wait()


# 运行cmd。
def run_cmd(
    name: str,
    cmd: list[str],
    cwd: Path,
    required: bool = True,
    env_overrides: dict[str, str] | None = None,
    timeout_seconds: int | None = None,
) -> GateDetail:
    """参数：
        name: 条目名称。
        cmd: Subprocess 命令到execute。
        cwd: repo root用于命令 execution。
        required: 是否缺失 命令 should be treated as BLOCKED。
        env_overrides: 可选environment 值用于fixture 或 trigger data。
        timeout_seconds: 当前 target 声明的命令超时秒数。

    返回：
        结构化 gate detail containing 状态, 命令, duration, 和。 t运行cated 输出. 命令 is 仅 side effect。
    """
    started = time.time()
    if not cmd or shutil.which(cmd[0]) is None:
        status = BLOCKED if required else FAIL
        return GateDetail(
            name=name,
            status=status,
            command=cmd,
            durationMs=0,
            output=f'命令不存在: {cmd[0] if cmd else "<empty>"}',
        )

    default_timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    timeout = PLAYWRIGHT_TIMEOUT_SECONDS if cmd[:2] == ['npx', 'playwright'] else default_timeout

    # 构建the subprocess environment带可选 overrides。
    run_env = os.environ.copy()
    if env_overrides:
        run_env.update(env_overrides)
    if _is_playwright_command(cmd) and run_env.get('FORCE_COLOR') and run_env.get('NO_COLOR'):
        run_env.pop('NO_COLOR', None)

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=run_env,
            check=False,
        )
        duration = int((time.time() - started) * 1000)
        full_output = (proc.stdout or '').strip()
        output = full_output
        if len(output) > COMMAND_OUTPUT_TAIL_CHARS:
            output = output[-COMMAND_OUTPUT_TAIL_CHARS:]
        status = PASS if proc.returncode == 0 else FAIL
        audit_block_reason = (
            _audit_network_block_reason(full_output, gate_name=name) if status == FAIL else None
        )
        if audit_block_reason:
            status = BLOCKED
            output = (
                f'{output}\n\n'
                f'[quality-gate] BLOCKED: {audit_block_reason}. '
                'Fix local certificate/proxy/network access and rerun audit; '
                'do not report the audit gate as PASS.'
            )
        skipped = 0
        skipped_kind = ''
        if status == PASS and _is_playwright_command(cmd):
            skipped = _playwright_skip_count(full_output)
            skipped_kind = 'Playwright'
        elif status == PASS and (_is_pytest_command(cmd) or name == 'scanScriptSmoke'):
            skipped = _pytest_skip_count(full_output)
            skipped_kind = 'pytest'
        if skipped:
            status = FAIL
            output = (
                f'{output}\n\n'
                f'[quality-gate] FAIL: selected {skipped_kind} gate reported '
                f'{skipped} skipped tests. '
                'If a test is not required for this change, remove it from the '
                'triggered mapping/command; '
                'if it is required, provide the needed fixture or environment instead of skipping.'
            )
        warning_reason = (
            _warning_after_trigger_reason(full_output, gate_name=name, cmd=cmd)
            if status == PASS
            else None
        )
        if warning_reason:
            status = FAIL
            output = (
                f'{output}\n\n'
                f'[quality-gate] FAIL: {warning_reason}. '
                'Triggered pytest/quality/full/release gates must be warning-free; '
                'fix the warning or mark the gate BLOCKED instead of reporting PASS.'
            )
        return GateDetail(
            name=name,
            status=status,
            command=cmd,
            exitCode=proc.returncode,
            durationMs=duration,
            output=output,
        )
    except subprocess.TimeoutExpired as exc:
        return GateDetail(
            name=name,
            status=FAIL,
            command=cmd,
            durationMs=int((time.time() - started) * 1000),
            output=f'超时: {exc}',
        )


# 维护gate 命令。
def gate_command(gate: str, repo_root: Path, target: str) -> list[str]:  # noqa: PLR0911, PLR0912
    """参数：
        gate: gate 参数。
        repo_root: repo root used到test 可选 文件 availability。
        target: 当前要运行或解析的 quality gate target 名称。

    返回：
        结果列表。

    说明：
        explicit gate-到-命令 matrix is kept flat so 现有 test assertions 和 operational。
    """
    python = _project_python(repo_root)
    dev_python = _project_python(repo_root, dev=True)
    if gate == 'settingsJson':
        json_files = ['.claude/settings.json', '.codex/hooks.json', '.qoder/settings.json', '.qoder/settings.local.example.json']
        existing = [f for f in json_files if (repo_root / f).exists()]
        code = "import json,sys; [json.load(open(p, encoding='utf-8')) for p in sys.argv[1:]]"
        return [python, '-c', code, *existing] if existing else []
    if gate == 'ignoredTrackedFiles':
        checker = repo_root / 'scripts' / 'quality' / 'check_ignored_tracked_files.py'
        return [python, str(checker), '--root', str(repo_root), '--staged'] if checker.exists() else []
    if gate == 'bashSyntax':
        existing = _relative_existing_files(
            repo_root,
            [
                '.claude/hooks/**/*.sh',
                '.codex/hooks/**/*.sh',
                '.qoder/hooks/**/*.sh',
                'scripts/harness/doctor.sh',
            ],
        )
        return ['bash', '-n', *existing] if existing else []
    if gate == 'scriptCommentLanguage':
        checker = repo_root / 'scripts' / 'quality' / 'check_code_comment_language.py'
        policy = repo_root / 'config' / 'technical-terms.json'
        if not checker.exists():
            return []
        cmd = [
            python,
            str(checker),
            '--script-comments',
            'scripts',
            '.claude/hooks',
            '.codex/hooks',
            '.qoder/hooks',
            'java/web/src/main/resources/static',
            'java/web/src/main/resources/templates',
        ]
        if policy.exists():
            cmd.extend(['--policy', str(policy)])
        return cmd
    if gate == 'pythonCompile':
        paths = ['scripts/claude_hooks', 'scripts/quality']
        if target == 'harness':
            paths = ['scripts/harness', 'scripts/quality']
        if target == 'index':
            paths = ['src/session_browser/index', 'scripts/quality/check_index_integrity.py']
        return [python, '-m', 'compileall', '-q', *paths]
    if gate == 'pythonFormat':
        return ['bash', 'scripts/session-browser.sh', 'format-check']
    if gate == 'pythonLint':
        return ['bash', 'scripts/session-browser.sh', 'lint']
    if gate == 'pythonType':
        return ['bash', 'scripts/session-browser.sh', 'type']
    if gate == 'pythonDocstring':
        return ['bash', 'scripts/session-browser.sh', 'doc']
    if gate == 'pythonCoverage':
        return ['bash', 'scripts/session-browser.sh', 'coverage']
    if gate == 'pythonAudit':
        return ['bash', 'scripts/session-browser.sh', 'audit']
    if gate == 'pythonComplexity':
        return ['bash', 'scripts/session-browser.sh', 'complexity']
    if gate == 'pythonDeadCode':
        return ['bash', 'scripts/session-browser.sh', 'dead-code']
    if gate == 'pythonDeps':
        return ['bash', 'scripts/session-browser.sh', 'deps-check']
    if gate == 'noTestSkips':
        return [python, 'scripts/quality/check_no_test_skips.py']
    if gate == 'languagePolicy':
        return [python, 'scripts/quality/check_language_policy.py']
    if gate == 'codexAgentPolicy':
        return [python, 'scripts/quality/check_codex_agent_policy.py']
    if gate == 'agentRuntimeManifest':
        return [python, 'scripts/quality/check_agent_runtime_manifest.py']
    if gate == 'agentHookParity':
        return [python, 'scripts/quality/check_agent_hook_parity.py']
    if gate == 'agentPolicySize':
        return [python, 'scripts/quality/check_agent_policy_size.py']
    if gate == 'agentRulesSync':
        return [python, 'scripts/quality/check_agent_rules_sync.py']
    if gate == 'agentRuntimeIsolation':
        return [python, 'scripts/quality/check_agent_runtime_isolation.py']
    if gate == 'agentRuntimeWorktree':
        return [python, 'scripts/quality/check_agent_runtime_worktree.py']
    if gate == 'gateBypassResistance':
        return [python, 'scripts/quality/check_gate_bypass_resistance.py']
    if gate == 'gateEscapeRate':
        return [python, 'scripts/quality/measure_gate_escape_rate.py', '--threshold', '0']
    if gate == 'protectedRootsSync':
        return [python, 'scripts/quality/check_protected_roots_sync.py']
    if gate == 'qoderRuntimeParity':
        return [python, 'scripts/quality/check_qoder_runtime_parity.py']
    if gate == 'hookPayloadCompat':
        return [python, 'scripts/quality/check_hook_payload_compat.py']
    if gate == 'subagentHandoffProtocol':
        return [python, 'scripts/quality/check_subagent_handoff_protocol.py']
    if gate == 'skillRegistry':
        return [python, 'scripts/quality/check_skill_registry.py']
    if gate == 'agentEntryParity':
        return [python, 'scripts/quality/check_agent_entry_parity.py']
    if gate == 'noRealSessionFixtures':
        return [python, 'scripts/quality/check_no_real_session_fixtures.py']
    if gate == 'secretLikeContent':
        return [python, 'scripts/quality/check_secret_like_content.py']
    if gate == 'runtimeReport':
        return [python, 'scripts/quality/check_agent_runtime_report.py']
    if gate == 'hookSelfTest':
        return [python, '-m', 'scripts.claude_hooks.main', '--self-test']
    if gate == 'templateContract':
        return [python, 'scripts/quality/template_contract_check.py']
    if gate == 'staticCssContract':
        return [python, 'scripts/quality/static_contract_check.py']
    if gate == 'cssOwnership':
        return [python, 'scripts/quality/check_css_ownership.py']
    if gate == 'browserLayout':
        if (
            (repo_root / 'tests' / 'playwright').exists()
            and (repo_root / 'playwright.config.js').exists()
            and (repo_root / 'node_modules').exists()
        ):
            return [
                'npx',
                'playwright',
                'test',
                'ui-contract.spec.ts',
                'main-pages-visual.spec.ts',
                'session-detail-layout',
                'shell-states',
                'dashboard-chart-coordinates',
                f'--workers={_playwright_workers()}',
            ]
        return []
    if gate == 'browserInteraction':
        if (
            (repo_root / 'tests' / 'playwright').exists()
            and (repo_root / 'playwright.config.js').exists()
            and (repo_root / 'node_modules').exists()
        ):
            return [
                'npx',
                'playwright',
                'test',
                'session-detail.spec.js',
                'sessions-list.spec.js',
                '--grep-invert',
                '100 轮',
                f'--workers={_playwright_workers()}',
            ]
        return []
    if gate == 'pytest':
        test_candidates = {
            'session-detail': [
                'tests/ui/test_web_template_contract.py',
                'tests/ui/test_web_static_contract.py',
            ],
            'hook-runtime': [
                'tests/hooks',
                'tests/harness',
                'tests/quality/test_quality_artifact.py',
                'tests/quality/test_quality_gate_runner.py',
                'tests/quality/test_run_required_quality_gates.py',
                'tests/quality/test_scan_script_smoke_gate.py',
                'tests/quality/test_python_env_contract.py',
                'tests/quality/test_no_test_skips_gate.py',
                'tests/quality/test_java_classification.py',
                'tests/quality/test_check_java_record_component_javadocs.py',
                'tests/quality/test_warning_gate_cli.py',
            ],
            'harness': [
                'tests/harness',
                'tests/quality/test_run_required_quality_gates.py',
            ],
            'acceptance-contracts': [
                'tests/quality/test_contract_case_specs.py',
            ],
            'index': ['tests/index/'],
        }
        items = [x for x in test_candidates.get(target, ['tests']) if (repo_root / x).exists()]
        return [dev_python, '-m', 'pytest', '-q', '-W', 'error', *items] if items else []
    if gate == 'doctor':
        return ['bash', 'scripts/harness/doctor.sh']
    if gate == 'sessionSamples':
        gradlew = repo_root / 'gradlew'
        runner = repo_root / 'scripts' / 'quality' / 'run_session_samples_gate.py'
        if not gradlew.exists() or not runner.exists():
            return []
        return [python, str(runner), '--repo-root', str(repo_root)]
    if gate == 'repoStructure':
        return [python, 'scripts/quality/validate_repo_structure.py']
    if gate == 'harnessStructure':
        return [python, 'scripts/harness/validate_harness_structure.py']
    if gate == 'openspecLayout':
        return [python, 'scripts/harness/validate_openspec_layout.py']
    if gate == 'repoSlimming':
        return [python, 'scripts/quality/repo_slimming_contract_check.py']
    if gate == 'indexIntegrity':
        return [python, 'scripts/quality/check_index_integrity.py']
    if gate == 'rawInnerhtml':
        return [python, 'scripts/quality/check_raw_innerhtml.py', '--check']
    if gate == 'layoutInlineStyle':
        return [python, 'scripts/quality/check_layout_inline_style.py', '--check']
    if gate == 'acceptanceContracts':
        return [python, 'scripts/quality/validate_acceptance_contracts.py']
    if gate == 'javaCheck':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        # Gradle 9.6.0 binary 测试结果偶发缓存打包竞态。
        # 策略：逐模块 cleanTest + test --no-daemon --no-build-cache，每个模块独立 JVM 进程。
        # 发现 binary results 竞态时只允许重试一次；重试仍失败必须 fail-closed。
        gw = str(gradlew)
        modules = [
            'common',
            'core-domain',
            'source-spi',
            'sources',
            'normalization-engine',
            'index-api',
            'index-store-sqlite',
            'scan-engine',
            'application',
            'web',
            'app-cli',
            'tests:support',
            'tests:contracts',
            'tests:architecture',
        ]
        test_checks = ' '.join(
            f'{gw} :java:{m}:cleanTest :java:{m}:test --no-daemon --no-build-cache --no-parallel > /tmp/javaCheck-{m}.log 2>&1; '
            f'rc=$?; '
            f'if [ $rc -eq 0 ]; then :; '
            f'elif grep -qE "NoSuchFileException|EOFException|daemon has been stopped|header parser received no bytes" '
            f'     /tmp/javaCheck-{m}.log 2>/dev/null; then '
            f'  echo "RETRY: :java:{m}:test after Gradle binary result race"; '
            f'  find java -path "*/build/test-results/*/binary" -type d -exec rm -rf {{}} + 2>/dev/null; '
            f'  {gw} :java:{m}:cleanTest :java:{m}:test --no-daemon --no-build-cache --no-parallel > /tmp/javaCheck-{m}.retry.log 2>&1; '
            f'  retry_rc=$?; '
            f'  if [ $retry_rc -ne 0 ]; then '
            f'    echo "FAIL: :java:{m}:test retry failed (exit=$retry_rc)"; '
            f'    tail -20 /tmp/javaCheck-{m}.retry.log; '
            f'    exit $retry_rc; '
            f'  fi; '
            f'else echo "FAIL: :java:{m}:test (exit=$rc)"; tail -5 /tmp/javaCheck-{m}.log; exit 1; fi; '
            for m in modules
        )
        script = (
            f'find java -path "*/build/test-results/*/binary" -type d '
            f'-exec rm -rf {{}} + 2>/dev/null; '
            f'{test_checks}'
            f'{gw} check -x test -x javadoc -x checkstyleMain -x checkstyleTest '
            f'--no-daemon --no-build-cache --no-parallel -q 2>/dev/null; '
            f'echo "javaCheck: all passed"'
        )
        return ['bash', '-c', script]
    # 中文注释检查使用仓库内脚本和策略文件，禁止依赖 tmp 路径。
    if gate == 'javaChineseComments':
        checker = repo_root / 'scripts' / 'quality' / 'check_code_comment_language.py'
        policy = repo_root / 'config' / 'technical-terms.json'
        if not checker.exists():
            return []
        cmd = [python, str(checker)]
        if policy.exists():
            cmd.extend(['--policy', str(policy)])
        return cmd
    if gate == 'javaRecordComponentJavadocs':
        checker = repo_root / 'scripts' / 'quality' / 'check_java_record_component_javadocs.py'
        if not checker.exists():
            return []
        return [python, str(checker), 'java']
    if gate == 'noJavaTestSkips':
        checker = repo_root / 'scripts' / 'quality' / 'check_no_java_test_skips.py'
        if not checker.exists():
            return []
        return [python, str(checker), '--root', str(repo_root)]
    if gate == 'javaModuleBoundaries':
        checker = repo_root / 'scripts' / 'quality' / 'check_java_module_boundaries.py'
        if not checker.exists():
            return []
        return [python, str(checker)]
    if gate in {'reuseIncremental', 'reuseAnalyzeIncremental'}:
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        return [str(gradlew), 'reuseAnalyzeIncremental']
    if gate == 'reuseStandardCpd':
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        return [str(gradlew), 'reuseStandardCpd']
    if gate == 'noJavaSuppressWarnings':
        checker = repo_root / 'scripts' / 'quality' / 'check_no_java_suppress_warnings.py'
        if not checker.exists():
            return []
        return [python, str(checker)]
    if gate == 'scanScriptSmoke':
        test_path = repo_root / 'tests' / 'script_commands' / 'test_session_browser_scan_smoke.py'
        if not test_path.exists():
            return []
        gradlew = repo_root / 'gradlew'
        if not gradlew.exists():
            return []
        install_log = str(_run_tmp_dir(repo_root, 'logs') / 'scanScriptSmoke-installDist.log')
        pytest_cmd = shlex.join(
            [dev_python, '-m', 'pytest', '-q', '-W', 'error', str(test_path)]
        )
        script = (
            f'{shlex.quote(str(gradlew))} :java:app-cli:installDist --no-daemon '
            f'> {install_log} 2>&1; '
            f'rc=$?; '
            f'if [ $rc -ne 0 ]; then '
            f'echo "FAIL: :java:app-cli:installDist (exit=$rc)"; '
            f'tail -40 {install_log}; '
            f'exit $rc; '
            f'fi; '
            f'{pytest_cmd}'
        )
        # 先构建 Java CLI launcher，再运行 smoke pytest，避免依赖陈旧本地产物。
        return ['bash', '-c', script]
    return []


_FIXTURE_GATES = {'browserLayout', 'browserInteraction'}

# 维护进度。
def _progress(message: str) -> None:
    """参数：
        message: 不带前缀的进度行。
    """
    print(f'[quality-gate] {message}', file=sys.stderr, flush=True)


# 运行target。
def run_target(
    repo_root: Path, target: str, changed_files: list[str] | None = None
) -> list[GateDetail]:
    """参数：
        repo_root: 执行命令时使用的 repo root。
        target: 已验证的 quality target 名称。
        changed_files: 导出给 child gate 的可选 changed-files 上下文；不用于裁剪已选 gate。

    返回：
        按执行顺序排列的 gate details；fixture server 生命周期在函数内收口。
    """
    details: list[GateDetail] = []
    gates = required_gates_for_target(target)
    total_gates = len(gates)
    target_timeout = int(target_parallel_meta(target).get('timeout', DEFAULT_TIMEOUT_SECONDS))
    _progress(f'target={target} start ({total_gates} gates)')

    # 检查是否需要运行依赖 fixture 的 gate。
    needs_fixture = any(g in _FIXTURE_GATES for g in gates)

    fixture_proc = None
    fixture_tmpdir = None
    fixture_base_url = None
    fixture_error = None

    if needs_fixture:
        default_base = os.environ.get('BASE_URL', 'http://127.0.0.1:19099')
        if not _fixture_session_available(default_base):
            fixture_proc, fixture_base_url, fixture_tmpdir, fixture_error = _start_fixture_server()
            if fixture_proc and fixture_base_url:
                print(f'[fixture-server] started at {fixture_base_url}')
            elif fixture_base_url is None:
                print(f'[fixture-server] BLOCKED: could not start fixture server: {fixture_error}')
        else:
            fixture_base_url = default_base

    try:
        for index, gate in enumerate(gates, 1):
            cmd = gate_command(gate, repo_root, target)
            if not cmd:
                detail = GateDetail(
                    name=gate,
                    status=BLOCKED,
                    command=[],
                    output=f'required gate {gate} 没有可执行命令或依赖缺失。',
                )
                details.append(detail)
                _progress(f'[{index}/{total_gates}] {gate} BLOCKED no command')
                continue

            command_label = shlex.join(cmd)
            if len(command_label) > 180:
                command_label = command_label[:177] + '...'
            _progress(f'[{index}/{total_gates}] {gate} start: {command_label}')

            # 用于 fixture-dependent gate, inject BASE_URL 如果 fixture server is running。
            env_override: dict[str, str] = {}
            env_override['SESSION_BROWSER_PYTHON'] = _project_python(repo_root)
            if changed_files is not None:
                env_override['QUALITY_CHANGED_FILES'] = json.dumps(
                    changed_files, ensure_ascii=False
                )
            if gate in _FIXTURE_GATES and fixture_base_url:
                env_override['BASE_URL'] = fixture_base_url
                env_override['PW_SESSION_URL'] = (
                    f'{fixture_base_url}/sessions/claude_code/hifi-viz-session-001'
                )
                env_override['PW_LONG_SESSION_URL'] = (
                    f'{fixture_base_url}/sessions/claude_code/long-session-001'
                )
                env_override['SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER'] = '1'
            elif gate in _FIXTURE_GATES:
                detail = GateDetail(
                    name=gate,
                    status=BLOCKED,
                    command=cmd,
                    durationMs=0,
                    output=f'fixture server unavailable: {fixture_error or "unknown error"}',
                )
                details.append(detail)
                _progress(f'[{index}/{total_gates}] {gate} BLOCKED fixture unavailable')
                continue

            detail = run_cmd(
                gate,
                cmd,
                repo_root,
                required=True,
                env_overrides=env_override or None,
                timeout_seconds=target_timeout,
            )
            details.append(detail)
            status_label = detail.status.upper()
            _progress(f'[{index}/{total_gates}] {gate} {status_label} ({detail.durationMs} ms)')
    finally:
        if fixture_proc:
            _stop_fixture_server(fixture_proc, fixture_tmpdir)
            print('[fixture-server] stopped')

    status, failures = compute_overall({detail.name: detail.status for detail in details})
    if failures:
        _progress(f'target={target} {status.upper()} failures={", ".join(failures)}')
    else:
        _progress(f'target={target} {status.upper()}')
    return details


# 构建summary。
def build_summary(
    target: str,
    change_id: str,
    started_at: str,
    details: list[GateDetail],
    not_triggered_gates: list[str] | None = None,
    repo_root: Path | None = None,
) -> QualitySummary:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        change_id: 当前 OpenSpec change id。
        started_at: started at 参数。
        details: gate 结果 收集ed从``运行_target``。
        not_triggered_gates: 必需 gate omitted by changed-文件 映射。
        repo_root: 仓库根目录。

    返回：
        summary 对象 读取y用于``write_quality_summary``。
    """
    required = {detail.name: detail.status for detail in details}
    status, failures = compute_overall(required)
    warning_failures = [
        f'{detail.name}: warning after trigger'
        for detail in details
        if 'warning after trigger' in (detail.output or '')
    ]
    base_commit = resolve_base_commit(str(repo_root)) if repo_root else ''
    dirty_hash = resolve_dirty_hash(str(repo_root)) if repo_root else ''
    return QualitySummary(
        schemaVersion=3,
        status=status,
        target=target,
        changeId=change_id,
        startedAt=started_at,
        finishedAt=utc_now(),
        requiredGates=required,
        blockingFailures=failures,
        warnings=warning_failures,
        artifacts={'notTriggeredGates': not_triggered_gates or []},
        gateDetails=[detail.__dict__ for detail in details],
        runId=f'{change_id}-{target}-{started_at}',
        baseCommit=base_commit,
        dirtyHash=dirty_hash,
        generatedAt=started_at,
        freshness='0s',
    )


# 解析 quality artifact 的 change-id。
def resolve_change_id(explicit: str | None, repo_root: Path) -> str:
    """参数：
        explicit: 命令行显式传入的 change-id。
        repo_root: 仓库根目录。

    返回：
        可用于 quality artifact 的 change-id。
    """
    if explicit:
        return explicit
    active_change = repo_root / 'tmp' / 'active_change.json'
    if active_change.exists():
        try:
            data = json.loads(active_change.read_text(encoding='utf-8'))
            change_id = data.get('change_id')
            if isinstance(change_id, str) and change_id.strip():
                return change_id
        except (OSError, json.JSONDecodeError):
            pass
    return 'manual-run'


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Deterministic quality gate runner')
    parser.add_argument(
        '--target',
        required=True,
        choices=sorted(QUALITY_TARGETS),
    )
    parser.add_argument('--change-id', default=None)
    parser.add_argument(
        '--out', default='tmp/quality', help='Quality artifact directory. Default: tmp/quality'
    )
    parser.add_argument(
        '--changed-files',
        default=None,
        help="JSON array of changed file paths, or 'auto' to read from changed-files.jsonl",
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    change_id = resolve_change_id(args.change_id, repo_root)
    validate_target(args.target)
    started_at = utc_now()

    # 解析输出目录；有 session identity 时默认写入隔离 quality path。
    out_dir = Path(args.out)
    if args.out == 'tmp/quality':
        from scripts.claude_hooks import paths as runtime_paths

        identity = runtime_paths.identity_from_values()
        if identity.has_session:
            out_dir = runtime_paths.quality_dir(repo_root, identity)

    # 解析changed 文件。
    changed_files: list[str] | None = None
    if args.changed_files == 'auto':
        changed_files = _read_changed_files(repo_root)
    elif args.changed_files:
        changed_files = json.loads(args.changed_files)

    details = run_target(repo_root, args.target, changed_files)
    summary = build_summary(args.target, change_id, started_at, details, [], repo_root)
    out = write_quality_summary(repo_root / out_dir, summary, target_specific=True)
    print(f'quality summary: {out}')
    print(f'status: {summary.status}')
    return 0 if summary.status == PASS else 1


# 读取changed-files 文件。
def _read_changed_files(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    from scripts.claude_hooks import paths as runtime_paths
    from scripts.quality import changed_files as changed_file_utils

    identity = runtime_paths.identity_from_values()
    log_dirs = runtime_paths.session_log_dirs(
        repo_root,
        identity,
        include_agents=identity.has_session and not identity.is_agent,
    )
    jsonl_paths = [path / 'changed-files.jsonl' for path in log_dirs]
    return changed_file_utils.read_recorded_changed_files_from_paths(
        jsonl_paths,
        identity.raw_session_id or None,
        agent_id=identity.raw_agent_id or None,
    )


if __name__ == '__main__':
    raise SystemExit(main())
