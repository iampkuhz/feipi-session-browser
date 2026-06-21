"""Validate template-level static contracts for the quality gate.

The scripts/quality dispatcher runs this CLI against repository templates. It
reads HTML files, reports contract failures on stdout, and exits non-zero when
Jinja delimiters or inline handlers would make browser rendering unsafe.
"""

from __future__ import annotations

from pathlib import Path


# 01. 模板契约检查
def check_templates(repo_root: Path) -> list[str]:
    """Inspect HTML templates for static rendering contract violations.

    Args:
        repo_root: Input value for repo_root.

    Returns:
        Computed result.
    """
    failures: list[str] = []
    templates = repo_root / 'src/session_browser/web/templates'
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


# 02. CLI
def main() -> int:
    """Run the template contract check as a CLI quality gate.

    Returns:
        Computed result.
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
