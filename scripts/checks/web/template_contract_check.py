"""检查 Jinja 模板的基础语法与事件绑定契约。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

from pathlib import Path

from scripts.checks._framework import repository_root

REPO_ROOT = repository_root()


def check_templates(repo_root: Path) -> list[str]:
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


def main() -> int:
    """解析命令行参数并运行脚本入口。"""

    root = Path.cwd()
    failures = check_templates(root)
    if failures:
        for item in failures:
            print(item)
        return 1
    print('template contract PASS')
    return 0
