#!/usr/bin/env python3
"""本模块负责执行 `check_js_action_handlers` 对应的确定性仓库检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

TEMPLATE_DIR = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'templates'
JS_DIR = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'js'

# 关键 action 必须存在 handler
CRITICAL_ACTIONS = {
    'toggle-all',  # 展开或收起全部项
    'status-failed',  # 失败状态筛选
    'toggle-round',  # 轮次延迟加载与切换
    'open-payload',  # 打开 payload 弹窗
    'payload-filter',  # payload 标签筛选与覆盖矩阵
    'tab-trace',  # trace 标签页
    'tab-payload',  # payload 标签页
}

# 触发模式：当变更文件匹配时运行此检查
TRIGGER_PATTERNS = [
    'java/web/src/main/resources/static/**/*.js',
]


# 提取模板声明的 action 名称。
def _extract_template_actions() -> dict[str, list[str]]:
    """返回：
    结果映射。
    """
    actions: dict[str, list[str]] = {}
    for html_file in TEMPLATE_DIR.rglob('*.html'):
        text = html_file.read_text(encoding='utf-8', errors='replace')
        found = re.findall(r'data-action="([^"]+)"', text)
        rel = html_file.relative_to(REPO_ROOT).as_posix()
        if found:
            actions[rel] = found
    return actions


# 提取JavaScript handlers。
def _extract_js_handlers() -> set[str]:
    """返回：
    解析后的 HookContext；失败时携带 parse_error。
    """
    handlers: set[str] = set()
    for js_file in JS_DIR.rglob('*.js'):
        text = js_file.read_text(encoding='utf-8', errors='replace')
        # 匹配 data-action 查找模式
        found = re.findall(
            r'(?:data-action|getAttribute\(["\']data-action["\']\)|dataset\.action)\s*["\'=]\s*["\']?([a-z][a-z0-9_-]*)',
            text,
        )
        # 更通用的：查找 action 字符串引用
        found2 = re.findall(r'["\']([a-z][a-z0-9_-]*)["\']\s*(?:===|==|\.includes|\.indexOf)', text)
        found2b = re.findall(r'\baction\b\s*(?:===|==)\s*["\']([a-z][a-z0-9_-]*)["\']', text)
        found2c = re.findall(r'\.dataset\.action\s*(?:===|==)\s*["\']([a-z][a-z0-9_-]*)["\']', text)
        found3 = re.findall(r'const\s+\w+Action\s*=\s*["\']([a-z][a-z0-9_-]*)["\']', text)
        found4 = re.findall(r'case\s+["\']([a-z][a-z0-9_-]*)["\']', text)
        handlers.update(found)
        handlers.update(found2)
        handlers.update(found2b)
        handlers.update(found2c)
        handlers.update(found3)
        handlers.update(found4)
        if "action.indexOf('tab-')" in text or 'action.indexOf("tab-")' in text:
            handlers.update({'tab-trace', 'tab-payload', 'tab-metrics'})
    return handlers


# 解析命令行参数并运行脚本入口。
def main() -> None:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    template_actions = _extract_template_actions()
    js_handlers = _extract_js_handlers()

    # 内置 action（浏览器行为或 CSS-only）不需要 JS handler
    built_in = {
        'sort',
        'page-input',
        'go-dashboard',
        'go-sessions',
        'run-scan',
        'open-project',
        'open-project-link',
        'open-agent',
        'clear-search',
        'info',
        'metric-info',
        'close-modal',
        'prev-page',
        'next-page',
        'nav-dashboard',
        'nav-projects',
        'nav-sessions',
        'nav-glossary',
        'payload-mode',
    }

    errors: list[str] = []
    critical_missing: list[str] = []

    all_actions: set[str] = set()
    for actions in template_actions.values():
        all_actions.update(actions)

    for action in sorted(all_actions):
        if action in built_in:
            continue
        if action not in js_handlers:
            if action in CRITICAL_ACTIONS:
                critical_missing.append(action)
                errors.append(f"[BLOCK] 关键 action '{action}' 无 JS handler")
            else:
                errors.append(f"[WARN] action '{action}' 无 JS handler")

    if critical_missing:
        print('')
        for e in errors:
            print(e)
        print(f'\n关键缺失: {", ".join(critical_missing)}')
        sys.exit(1)
    else:
        print(f'[PASS] 全部 {len(all_actions)} 个 data-action 均有 handler 或豁免。')
        sys.exit(0)


if __name__ == '__main__':
    main()
