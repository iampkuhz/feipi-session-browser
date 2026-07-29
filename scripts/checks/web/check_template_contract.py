"""检查 Jinja 模板的基础闭合语法与 inline onclick 禁令。

未闭合的模板标记会破坏渲染，inline onclick 会绕过静态 JavaScript 绑定约束。唯一公开入口是
`check(arguments)`；失败表示模板目录不可用或至少一个模板违反这些契约。
"""

from __future__ import annotations

from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()


def _check_templates(repo_root: Path) -> list[str]:
    """返回模板缺失、括号未闭合或使用 inline onclick 的诊断。"""
    failures: list[str] = []
    templates = repo_root / 'java/web/src/main/resources/templates'
    if not templates.exists():
        return [f'模板目录不存在:{templates}']

    html_files = list(templates.rglob('*.html'))
    if not html_files:
        return [f'模板目录没有 html 文件:{templates}']

    for path in html_files:
        text = path.read_text(encoding='utf-8', errors='replace')
        rel = path.relative_to(repo_root).as_posix()
        if '{%' in text and '%}' not in text:
            failures.append(f'{rel}: Jinja block 可能未闭合.')
        if '{{' in text and '}}' not in text:
            failures.append(f'{rel}: Jinja expression 可能未闭合.')
        if 'onclick=' in text:
            failures.append(f'{rel}: 禁止 inline onclick,改用 static JS 绑定.')
    return failures


def check(arguments: list[str]) -> CheckResult:
    """解析统一 CLI 参数，并按模板遍历顺序返回语法或事件绑定失败。"""
    parser = argument_parser(description='检查 Jinja 模板基础契约')
    parser.parse_args(arguments)
    root = Path.cwd()
    failures = _check_templates(root)
    return CheckResult.from_errors(failures)
