"""提供 template contract 检查 脚本能力。"""

from __future__ import annotations

from pathlib import Path


# 检查templates。
def check_templates(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        Computed 结果。
    """
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


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        Computed 结果。
    """
    root = Path.cwd()
    failures = check_templates(root)
    if failures:
        for item in failures:
            print(item)
        return 1
    print('template contract PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
