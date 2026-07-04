#!/usr/bin/env python3
"""提供 validate primitive screenshots 脚本能力。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PRIMITIVE_REFERENCES = ROOT / 'qa' / 'screenshots' / 'primitive-references'
PRIMITIVE_ACTUALS = ROOT / 'test-results' / 'primitive-screenshots'

CANONICAL_PRIMITIVES = [
    'button',
    'icon_button',
    'badge',
    'metric_card',
    'metric_grid',
    'pagination',
    'token_bar',
    'tooltip',
    'popover',
    'section_card',
    'data_table',
    'filter_bar',
    'payload_modal',
    'empty_state',
    'error_state',
]

ALL_PRIMITIVES = CANONICAL_PRIMITIVES

# 默认 viewport用于screenshot capture。
VIEWPORT = {'width': 800, 'height': 600}

# 默认 server port (matches session-browser.sh 默认)。
DEFAULT_PORT = 18999
SIZE_RATIO_TOLERANCE = 0.3


# 读取primitive render args。
def get_primitive_render_args(name: str) -> dict:
    """参数：
        name: 条目名称。

    返回：
        结果映射。
    """
    args: dict = {
        'button': {'label': 'Primary Action', 'variant': 'primary'},
        'icon_button': {'icon': '&#9998;'},
        'badge': {'label': 'info', 'variant': 'info'},
        'metric_card': {'label': 'Sessions', 'value': '42'},
        'metric_grid': {
            'cards': [
                '<div class="metric-card"><span class="metric-label">A</span>'
                '<span class="metric-value">10</span></div>',
                '<div class="metric-card"><span class="metric-label">B</span>'
                '<span class="metric-value">20</span></div>',
            ]
        },
        'pagination': {'current_page': 2, 'total_pages': 5},
        'token_bar': {
            'segments': [
                {'kind': 'fresh', 'count': 1000},
                {'kind': 'read', 'count': 2000},
                {'kind': 'write', 'count': 500},
            ],
            'total': 3500,
        },
        'tooltip': {'content': 'Tooltip content', 'trigger_text': 'Hover me'},
        'popover': {'content': 'Popover body', 'trigger_element': 'Click me'},
        'section_card': {'title': 'Section', 'content': '<p>Body text</p>'},
        'data_table': {
            'headers': ['Name', 'Value', 'Status'],
            'rows': [
                ['Alpha', '100', 'active'],
                ['Beta', '200', 'inactive'],
            ],
        },
        'filter_bar': {
            'filters': [
                {'name': 'status', 'label': 'Status', 'options': ['active', 'inactive']},
            ]
        },
        'payload_modal': {'payload_id': 'test-1', 'title': 'Test Payload', 'kind': 'tool_call'},
        'empty_state': {'message': 'No results found'},
        'error_state': {'message': 'Something went wrong'},
    }
    return args.get(name, {})


class DevServer:
    """表示 DevServer。
    """

    # 维护init。
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        """参数：
            port: 本地服务端口。
        """
        self.port = port
        self.process: subprocess.Popen | None = None

    # 维护启动。
    def start(self) -> bool:
        """返回：
            满足条件时返回 true，否则返回 false。
        """
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    '-m',
                    'session_browser',
                    'serve',
                    '--allow-empty',
                    '--host',
                    '127.0.0.1',
                    '--port',
                    str(self.port),
                    '--startup-scan',
                ],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**_clean_env(), 'PYTHONUNBUFFERED': '1'},
            )
            # 等待用于 server到be ready。
            for _ in range(30):
                time.sleep(0.5)
                if _is_server_ready(self.port):
                    return True
            print(f'  WARN: Server did not become ready on port {self.port}')
            return False
        except FileNotFoundError:
            print('  SKIP: session_browser module not found')
            return False

    # 维护stop。
    def stop(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


# 维护clean 环境。
def _clean_env() -> dict:
    """返回：
        结果映射。
    """
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT / 'src') + ':' + env.get('PYTHONPATH', '')
    return env


# 判断是否server ready。
def _is_server_ready(port: int) -> bool:
    """参数：
        port: 本地服务端口。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    try:
        urllib.request.urlopen(f'http://127.0.0.1:{port}', timeout=1)
        return True
    except Exception:
        return False


# 确保Playwright。
def ensure_playwright() -> bool:
    """返回：
        满足条件时返回 true，否则返回 false。
    """
    result = subprocess.run(
        ['npx', 'playwright', '--version'],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        print(f'  Playwright {result.stdout.strip()}')
        return True
    print('  SKIP: Playwright not installed (run: npm install && npx playwright install)')
    return False


# 维护capture primitive 截图。
def capture_primitive_screenshots(
    primitives: list[str],
    port: int = DEFAULT_PORT,
    output_dir: Path | None = None,
    capture_only: bool = False,
) -> dict:
    """参数：
        primitives: primitives 参数。
        port: 本地服务端口。
        output_dir: 可选目录用于generated screenshots; defaults到test-结果。
        capture_only: capture only 参数。

    返回：
        映射 keyed by primitive name带pass, fail, 或 skip 状态 和 diagnostic details。
    """
    results: dict = {}
    base_dir = output_dir or PRIMITIVE_ACTUALS
    base_dir.mkdir(parents=True, exist_ok=True)

    if not ensure_playwright():
        for name in primitives:
            results[name] = {'status': 'skip', 'details': 'Playwright not available'}
        return results

    for name in primitives:
        ref_path = PRIMITIVE_REFERENCES / f'{name}-reference.png'
        actual_path = base_dir / f'{name}-actual.png'

        # 检查如果 reference exists。
        has_reference = ref_path.exists()

        if not has_reference and not capture_only:
            results[name] = {
                'status': 'skip',
                'details': 'No reference image available',
            }
            continue

        # 生成screenshot via Playwright。
        pw_result = _take_screenshot_with_playwright(
            name,
            url=f'http://127.0.0.1:{port}/__primitives__/{name}',
            output_path=str(actual_path),
        )

        if pw_result['success']:
            if has_reference and not capture_only:
                diff = _compare_images(str(ref_path), str(actual_path))
                results[name] = {
                    'status': 'pass' if diff['pass'] else 'fail',
                    'details': diff.get('message', 'matched'),
                }
            else:
                results[name] = {
                    'status': 'pass' if capture_only else 'skip',
                    'details': 'Screenshot captured (no reference to compare)',
                }
        else:
            results[name] = {
                'status': 'fail',
                'details': pw_result.get('error', 'screenshot failed'),
            }

    return results


# 维护take 截图 Playwright。
def _take_screenshot_with_playwright(
    name: str,
    url: str,
    output_path: str,
) -> dict:
    """参数：
        name: 用于诊断信息的 primitive 名称。
        url: 隔离渲染 primitive 的本地浏览器 URL。
        output_path: Playwright 写入 PNG 的文件系统路径。

    返回：
        包含状态和命令输出详情的结果映射。
    """
    spec = f"""
const {{ test, expect }} = require('@playwright/test');
test('{name} primitive screenshot', async ({{ page }}) => {{
  await page.setViewportSize({{ width: {VIEWPORT['width']}, height: {VIEWPORT['height']} }});
  await page.goto('{url}');
  await page.waitForLoadState('networkidle');
  await page.screenshot({{ path: '{output_path}', fullPage: true }});
}});
"""
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.spec.js',
        dir=str(ROOT / 'tests' / 'playwright'),
        delete=False,
    ) as f:
        f.write(spec)
        spec_path = f.name

    try:
        result = subprocess.run(
            ['npx', 'playwright', 'test', spec_path, '--reporter=list'],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
            check=False,
        )
        return {
            'success': result.returncode == 0,
            'error': result.stderr.strip() if result.returncode != 0 else '',
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Playwright timed out'}
    finally:
        Path(spec_path).unlink(missing_ok=True)


# 比较图像。
def _compare_images(ref_path: str, actual_path: str) -> dict:
    """参数：
        ref_path: 期望的 reference PNG 路径。
        actual_path: 实际捕获的 screenshot PNG 路径。

    返回：
        包含通过状态和比较详情的结果映射。
    """
    ref = Path(ref_path)
    actual = Path(actual_path)

    if not actual.exists():
        return {'pass': False, 'message': 'Actual screenshot missing'}
    if not ref.exists():
        return {'pass': False, 'message': 'Reference screenshot missing'}

    # 当前 harness 先用文件大小做基础 sanity check。
    ref_size = ref.stat().st_size
    actual_size = actual.stat().st_size

    if actual_size == 0:
        return {'pass': False, 'message': 'Actual screenshot is empty'}

    size_ratio = abs(ref_size - actual_size) / max(ref_size, 1)
    if size_ratio < SIZE_RATIO_TOLERANCE:
        return {'pass': True, 'message': f'Size ratio within tolerance ({size_ratio:.1%})'}
    return {
        'pass': False,
        'message': f'Size difference too large ({size_ratio:.1%}), pixel comparison needed',
    }


# 打印报告。
def print_report(results: dict, capture_only: bool = False) -> bool:
    """参数：
        results: results 参数。
        capture_only: 是否the 运行 仅 captured screenshots 和 skipped 比较。

    返回：
        当no primitive 失败; 当 at least one 比较 或 capture 失败.时返回 true。
    """
    mode = 'Capture' if capture_only else 'Validation'
    print(f'\n{"=" * 60}')
    print(f'Primitive Screenshot {mode} Report')
    print(f'{"=" * 60}')

    passed = 0
    failed = 0
    skipped = 0

    for name, result in sorted(results.items()):
        status = result['status'].upper()
        details = result.get('details', '')
        marker = {
            'PASS': '[PASS]',
            'FAIL': '[FAIL]',
            'SKIP': '[SKIP]',
        }.get(status, '[????]')

        print(f'  {marker:8s} {name:20s} {details}')

        if status == 'PASS':
            passed += 1
        elif status == 'FAIL':
            failed += 1
        else:
            skipped += 1

    total = passed + failed + skipped
    print(f'\n{"=" * 60}')
    print(f'Total: {total} | Pass: {passed} | Fail: {failed} | Skip: {skipped}')
    print(f'{"=" * 60}')

    if skipped > 0:
        print(f'\nMissing reference images for {skipped} primitives.')
        print('Run with --capture to generate baseline screenshots.')

    return failed == 0


# ── CLI ───────────────────────────────────────────────────────────────────


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码: 0用于a successful capture/列表/validation, 1用于validation 失败项。
    """
    parser = argparse.ArgumentParser(
        description='Validate primitive screenshots against HIFI references.',
    )
    parser.add_argument(
        '--primitive',
        '-p',
        help='Validate a single primitive (default: all)',
    )
    parser.add_argument(
        '--capture',
        '-c',
        action='store_true',
        help='Capture new screenshots without comparing',
    )
    parser.add_argument(
        '--list',
        '-l',
        action='store_true',
        help='List all primitives and exit',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=DEFAULT_PORT,
        help=f'Dev server port (default: {DEFAULT_PORT})',
    )
    parser.add_argument(
        '--output',
        '-o',
        type=Path,
        default=None,
        help='Output directory for screenshots',
    )
    parser.add_argument(
        '--no-server',
        action='store_true',
        help='Do not start the dev server (use existing)',
    )

    args = parser.parse_args()

    # 列出mode。
    if args.list:
        print('Canonical primitives (15):')
        for name in CANONICAL_PRIMITIVES:
            args_dict = get_primitive_render_args(name)
            print(f'  - {name}: {json.dumps(args_dict)}')
        print(f'\nTotal: {len(ALL_PRIMITIVES)} primitives')

        # 检查现有 references。
        ref_count = sum(1 for p in PRIMITIVE_REFERENCES.glob('*.png'))
        print(f'Existing references: {ref_count}/{len(ALL_PRIMITIVES)}')
        return 0

    if args.primitive:
        if args.primitive not in ALL_PRIMITIVES:
            print(f"ERROR: Unknown primitive '{args.primitive}'")
            print('Run --list to see available primitives')
            return 1
        primitives = [args.primitive]
    else:
        primitives = ALL_PRIMITIVES

    server = DevServer(port=args.port)
    try:
        if not args.no_server:
            print(f'Starting dev server on port {args.port}...')
            if not server.start():
                print('ERROR: Could not start dev server')
                return 1
            print(f'  Server ready on http://127.0.0.1:{args.port}')

        results = capture_primitive_screenshots(
            primitives=primitives,
            port=args.port,
            output_dir=args.output,
            capture_only=args.capture,
        )

        ok = print_report(results, capture_only=args.capture)
        return 0 if ok else 1

    finally:
        if not args.no_server:
            server.stop()


if __name__ == '__main__':
    sys.exit(main())
