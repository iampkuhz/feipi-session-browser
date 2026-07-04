#!/usr/bin/env python3
"""提供 log change evidence 脚本能力。"""

import json
import sys
from datetime import datetime, timezone
from functools import cache
from io import StringIO
from pathlib import Path

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
EVIDENCE_DIR = Path('tmp/task-evidence')
ACTIVE_CHANGE = Path('tmp/active_change.json')

DEBUG = '--debug' in sys.argv


# 读取stdin payload。
@cache
def _get_stdin_payload() -> dict | None:
    """返回：
        已解析的JSON payload, 或 None 当 stdin is 空 或 无效。
    """
    if sys.stdin.isatty():
        return None
    try:
        raw = sys.stdin.read()
        obj = _try_parse_json(raw)
        if obj is not None:
            return obj
    except (OSError, UnicodeDecodeError):
        pass
    return None


# 加载active change。
def load_active_change() -> dict | None:
    """返回：
        已解析的metadata 当 change id 存在, 否则 None。
    """
    if not ACTIVE_CHANGE.is_file():
        return None
    try:
        data = json.loads(ACTIVE_CHANGE.read_text(encoding='utf-8'))
        cid = data.get('change_id')
        if cid:
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


# 维护try parse JSON。
def _try_parse_json(text: str) -> dict | None:
    """参数：
        text: 待检查的文本。

    返回：
        已解析的dictionary 当 payload is JSON 对象, 否则 None。
    """
    text = text.strip()
    if not text.startswith('{'):
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, OSError):
        pass
    return None


# 提取payload。
def _extract_from_payload(payload: dict) -> tuple[str | None, str | None]:
    """参数：
        payload: payload 参数。

    返回：
        由文件路径 和 tool name,带缺失 值 as None.组成的 tuple。
    """
    file_path = None
    tool_name = None

    tool_name = payload.get('tool_name') or payload.get('tool')

    tool_input = payload.get('tool_input')
    if isinstance(tool_input, dict):
        file_path = (
            tool_input.get('file_path') or tool_input.get('path') or tool_input.get('notebook_path')
        )
    if not file_path:
        file_path = payload.get('file_path') or payload.get('path')

    return file_path, tool_name


# 读取文件 路径。
def get_file_path() -> str | None:
    """返回：
        文件路径到日志, 或 None 当 hook payload has no target。
    """
    if len(sys.argv) > 1 and sys.argv[1] not in ('--self-test', '--debug'):
        return sys.argv[1]

    payload = _get_stdin_payload()
    if payload is not None:
        fp, tn = _extract_from_payload(payload)
        if DEBUG and tn:
            print(f'[debug] resolved tool_name={tn} from stdin', file=sys.stderr)
        if fp:
            return fp

    return None


# 读取tool name。
def get_tool_name() -> str:
    """返回：
        get tool name 字符串。
    """
    payload = _get_stdin_payload()
    if payload is not None:
        _, tn = _extract_from_payload(payload)
        if tn:
            return tn

    return 'Write'


# 维护log entry。
def log_entry(file_path: str, tool: str, change_id: str | None) -> Path:
    """参数：
        file_path: Edited 文件路径 reported by hook。
        tool: tool 参数。
        change_id: Active OpenSpec change id, 如果 one is 可用。

    返回：
        路径到 JSONL evidence 文件 that received entry。
    """
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / f'{change_id}.jsonl' if change_id else EVIDENCE_DIR / 'unknown.jsonl'
    entry = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'tool': tool,
        'file_path': file_path,
        'change_id': change_id or 'unknown',
    }
    with target.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    return target


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    if '--self-test' in sys.argv:
        return self_test()

    file_path = get_file_path()
    if not file_path:
        # Nothing到日志, but 不 an 错误 (exit 0 by contract)。
        return 0

    tool = get_tool_name()
    change_data = load_active_change()
    change_id = change_data['change_id'] if change_data else None
    log_entry(file_path, tool, change_id)
    return 0


# 维护self test。
def self_test() -> int:  # noqa: PLR0915
    """返回：
        全部自测通过时返回 0，否则返回 1。
    """
    passed = 0
    failed = 0

    # 维护检查。
    def check(name: str, condition: bool) -> None:
        """参数：
            name: 便于阅读的断言名称。
            condition: 表示断言是否通过。
        """
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f'  [PASS] {name}')
        else:
            failed += 1
            print(f'  [FAIL] {name}')

    # 用例 1：argv 原始路径仍可写入 evidence。
    print('Test 1: argv raw path writes evidence')
    _reset_evidence()
    active = load_active_change()
    test_id = active['change_id'] if active else '_selftest_'
    fp = 'src/example/file.py'
    log_entry(fp, 'Edit', test_id)
    ev = EVIDENCE_DIR / f'{test_id}.jsonl'
    check('evidence file created', ev.is_file())
    if ev.is_file():
        entry = json.loads(ev.read_text().strip().split('\n')[-1])
        check('file_path matches', entry.get('file_path') == 'src/example/file.py')
        check('tool is Edit', entry.get('tool') == 'Edit')

    # 用例 2：从 stdin 读取 Claude Code 风格 payload。
    print('Test 2: stdin JSON payload (Claude Code style)')
    _reset_evidence()
    payload = json.dumps(
        {
            'tool_name': 'Edit',
            'tool_input': {'file_path': 'src/session_browser/web/static/style.css'},
        }
    )
    fp, tn = _simulate_stdin(payload)
    check('extracts tool_name from stdin', tn == 'Edit')
    check('extracts file_path from stdin', fp == 'src/session_browser/web/static/style.css')

    # 用例 3：MultiEdit payload 只生成一条 evidence。
    print('Test 3: MultiEdit payload - single evidence entry')
    _reset_evidence()
    multi_payload = json.dumps(
        {
            'tool_name': 'MultiEdit',
            'tool_input': {
                'file_path': 'src/multi.html',
                'edits': [{'file_path': 'src/a.html'}, {'file_path': 'src/b.html'}],
            },
        }
    )
    fp, tn = _simulate_stdin(multi_payload)
    check('tool_name is MultiEdit', tn == 'MultiEdit')
    check('file_path is top-level, not first edit', fp == 'src/multi.html')

    # 用例 4：没有活跃变更时写入 unknown.jsonl。
    print('Test 4: no active change writes to unknown.jsonl')
    _reset_evidence()
    backup = None
    if ACTIVE_CHANGE.is_file():
        backup = ACTIVE_CHANGE.read_bytes()
        ACTIVE_CHANGE.unlink()
    log_entry('docs/README.md', 'Write', None)
    unknown = EVIDENCE_DIR / 'unknown.jsonl'
    check('unknown.jsonl created', unknown.is_file())
    if unknown.is_file():
        entry = json.loads(unknown.read_text().strip().split('\n')[-1])
        check('change_id is unknown', entry.get('change_id') == 'unknown')
        check('file_path correct', entry.get('file_path') == 'docs/README.md')
    if backup is not None:
        ACTIVE_CHANGE.write_bytes(backup)

    # 用例 5：回退读取 notebook_path。
    print('Test 5: notebook_path extraction')
    _reset_evidence()
    nb_payload = json.dumps(
        {'tool_name': 'NotebookEdit', 'tool_input': {'notebook_path': 'analysis.ipynb'}}
    )
    fp, tn = _simulate_stdin(nb_payload)
    check('extracts notebook_path', fp == 'analysis.ipynb')

    # 用例 6：回退读取顶层路径字段。
    print('Test 6: top-level path fallback (no tool_input)')
    _reset_evidence()
    flat_payload = json.dumps({'tool': 'Write', 'file_path': 'config.yaml'})
    fp, tn = _simulate_stdin(flat_payload)
    check('extracts top-level file_path', fp == 'config.yaml')
    check('extracts top-level tool', tn == 'Write')

    # 结果汇总。
    print(f'\n{"=" * 60}')
    print(f'self-test results: {passed}/{passed + failed} passed')
    print(f'{"=" * 60}')
    return 0 if failed == 0 else 1


# 重置evidence。
def _reset_evidence() -> None:
    if EVIDENCE_DIR.is_dir():
        for f in EVIDENCE_DIR.iterdir():
            f.unlink()


# 维护模拟 stdin。
def _simulate_stdin(json_str: str) -> tuple[str | None, str | None]:
    """参数：
        json_str: 待解析的 JSON hook payload。

    返回：
        提取出的文件路径和 tool name。
    """
    saved_stdin = sys.stdin
    sys.stdin = StringIO(json_str)
    try:
        # 直接复用 main 路径中的 payload 解析逻辑。
        obj = _try_parse_json(json_str)
        if obj is not None:
            return _extract_from_payload(obj)
    finally:
        sys.stdin = saved_stdin
    return None, None


if __name__ == '__main__':
    sys.exit(main())
