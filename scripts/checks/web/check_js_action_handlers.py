"""检查模板关键 action 与 JavaScript handler 是否成对存在。

关键交互若只有模板声明而没有 handler，页面操作会静默失效。唯一公开入口是
`check(arguments)`；失败表示至少一个受保护 action 缺少可识别的实现。
"""

from __future__ import annotations

import re

from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()


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
BUILT_IN_ACTIONS = {
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


def _extract_template_actions() -> dict[str, list[str]]:
    """按模板路径收集其声明的 action 名称。"""
    actions: dict[str, list[str]] = {}
    for html_file in TEMPLATE_DIR.rglob('*.html'):
        text = html_file.read_text(encoding='utf-8', errors='replace')
        found = re.findall(r'data-action="([^"]+)"', text)
        rel = html_file.relative_to(REPO_ROOT).as_posix()
        if found:
            actions[rel] = found
    return actions


def _extract_js_handlers() -> set[str]:
    """从 JavaScript 的 action 分派模式中收集已实现的 handler 名称。"""
    patterns = (
        r'(?:data-action|getAttribute\(["\']data-action["\']\)|dataset\.action)\s*["\'=]\s*["\']?([a-z][a-z0-9_-]*)',
        r'["\']([a-z][a-z0-9_-]*)["\']\s*(?:===|==|\.includes|\.indexOf)',
        r'\baction\b\s*(?:===|==)\s*["\']([a-z][a-z0-9_-]*)["\']',
        r'\.dataset\.action\s*(?:===|==)\s*["\']([a-z][a-z0-9_-]*)["\']',
        r'const\s+\w+Action\s*=\s*["\']([a-z][a-z0-9_-]*)["\']',
        r'case\s+["\']([a-z][a-z0-9_-]*)["\']',
    )
    handlers: set[str] = set()
    for js_file in JS_DIR.rglob('*.js'):
        text = js_file.read_text(encoding='utf-8', errors='replace')
        for pattern in patterns:
            handlers.update(re.findall(pattern, text))
        if "action.indexOf('tab-')" in text or 'action.indexOf("tab-")' in text:
            handlers.update({'tab-trace', 'tab-payload', 'tab-metrics'})
    return handlers


def _check_action_handlers() -> list[str]:
    """返回缺失 handler 的关键 template action；无法识别时按缺失处理。"""
    handlers = _extract_js_handlers()
    actions = {action for values in _extract_template_actions().values() for action in values}
    return [
        f"关键 action '{action}' 无 JS handler"
        for action in sorted(actions - handlers - BUILT_IN_ACTIONS)
        if action in CRITICAL_ACTIONS
    ]


def check(arguments: list[str]) -> CheckResult:
    """解析统一 CLI 参数，并把缺失的关键 handler 按 action 排序返回。"""
    parser = argument_parser(description='核对模板关键 action 的 JavaScript handler')
    parser.parse_args(arguments)
    return CheckResult.from_errors(_check_action_handlers())
