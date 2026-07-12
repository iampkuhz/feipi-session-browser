#!/usr/bin/env python3
"""P0 门禁：UI 排序按钮统一性、页面脚本加载、sidebar nav 和脏选择器检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

TEMPLATES_DIR = REPO_ROOT / 'src' / 'session_browser' / 'web' / 'templates'
CSS_DIR = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'css'
JS_DIR = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'js'

# 触发模式：当变更文件匹配时运行此检查
TRIGGER_PATTERNS = [
    'java/web/src/main/resources/static/**',
    'java/web/src/main/resources/templates/**',
]


# 检查page scripts。
def check_page_scripts() -> list[str]:
    """返回：
    结果列表。
    """
    errors: list[str] = []
    checks = [
        ('projects.html', 'projects.js'),
    ]
    for template_name, js_name in checks:
        tmpl = TEMPLATES_DIR / template_name
        if not tmpl.exists():
            errors.append(f'[BLOCK] 模板 {template_name} 不存在')
            continue
        text = tmpl.read_text(encoding='utf-8')
        # 检查是否在 script_extra block 中加载了对应 JS
        if js_name not in text:
            errors.append(f'[BLOCK] {template_name} 未在 script_extra 中加载 {js_name}')
    return errors


# 检查排序控件是否使用统一契约。
def check_sort_unification() -> list[str]:
    """返回：
        结果列表。

    说明：
        禁止以下旧选择器在 CSS/JS/模板中存活：。
        但允许它们出现在注释中（作为历史记录）。
    """
    errors: list[str] = []
    banned_patterns = [
        r'\.sort-button\b',
        r'\.sortable-header\b',
        r'\.sort-caret\b',
        r'\.sort-mark\b',
        r'\.sessions-sort-icon\b',
        r'\.sessions-th__sort-btn\b',
    ]
    canonical = 'c-data-table__sort'
    for ext_dir, ext in [
        (CSS_DIR, '*.css'),
        (JS_DIR, '*.js'),
        (TEMPLATES_DIR, '*.html'),
    ]:
        for f in ext_dir.rglob(ext):
            text = f.read_text(encoding='utf-8', errors='replace')
            # 移除注释内容，只检查代码
            # CSS 注释: /* ... */
            code = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
            # HTML/Jinja 注释: {# ... #} 和 <!-- ... -->
            code = re.sub(r'\{#.*?#\}', '', code, flags=re.DOTALL)
            code = re.sub(r'<!--.*?-->', '', code, flags=re.DOTALL)
            # JS 注释: // ... 和 /* ... */
            code = re.sub(r'//.*?$', '', code, flags=re.MULTILINE)
            code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

            rel = f.relative_to(REPO_ROOT)
            for pat in banned_patterns:
                if re.search(pat, code):
                    # 检查是否也在同一文件中存在 canonical class
                    if canonical not in text:
                        errors.append(
                            f'[BLOCK] {rel} 仍使用旧排序选择器 {pat} '
                            f'且未迁移到 canonical {canonical}'
                        )
    return errors


# 检查无 duplicate th rules。
def check_no_duplicate_th_rules() -> list[str]:
    """返回：
        结果列表。

    说明：
        允许一个 canonical。data-table th 定义和一个。data-table thead th 定义，。
        但不允许多个顶级。data-table th {。 } rule（来自 style.css 迁移的重复项）。
    """
    errors: list[str] = []
    tables_css = CSS_DIR / 'ui-primitives' / '_tables.css'
    if not tables_css.exists():
        errors.append(f'[BLOCK] _tables.css 不存在: {tables_css}')
        return errors

    text = tables_css.read_text(encoding='utf-8')
    # 移除注释
    code = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # 统计非嵌套的 .data-table th { 规则（不含 .data-table th. 带修饰符的）
    # 匹配: 行首(或空白)后跟 .data-table th {
    # 排除数据表头等合法复合选择器
    # 同时排除数据表 thead 表头
    pattern = r'(?<![.\w])\.data-table\s+th\s*\{'
    matches = list(re.finditer(pattern, code))

    if len(matches) > 2:  # 允许 canonical + thead 两个
        errors.append(
            f'[BLOCK] _tables.css 中发现 {len(matches)} 个 .data-table th rule，'
            f'超过允许的上限 (2)。请删除重复迁移项。'
        )
    return errors


# 检查dirty CSS ban。
def check_dirty_css_ban() -> list[str]:
    """返回：
        结果列表。

    说明：
        禁止:。
        - projects.css 中定义共享 primitive (如。btn,。data-table th 等)。
        但命名空间内的覆盖 (.p-projects。tokenbar) 不算违规。
    """
    errors: list[str] = []
    banned_comments = [
        r'legacy\s+alias',
        r'compat\s+alias',
    ]
    for css_file in ['projects.css']:
        f = CSS_DIR / css_file
        if not f.exists():
            continue
        text = f.read_text(encoding='utf-8')
        rel = f.relative_to(REPO_ROOT)
        # 检查脏注释
        for pat in banned_comments:
            if re.search(pat, text, re.IGNORECASE):
                errors.append(f'[BLOCK] {rel} 包含禁止的注释模式: {pat}')
        # 检查共享 primitive 重写：逐行检查
        for line in text.splitlines():
            stripped = line.strip()
            # 跳过注释和空行
            if (
                stripped.startswith('/*')
                or stripped.startswith('*')
                or stripped.startswith('//')
                or not stripped
            ):
                continue
            # 如果行以 .p-projects 或 .p-agents 开头，说明在命名空间内，跳过
            if stripped.startswith('.p-projects') or stripped.startswith('.p-agents'):
                continue
            # 检查是否定义了共享 primitive（顶级规则，无命名空间前缀）
            # 使用简单匹配：行首直接是 .btn {, .data-table th { 等
            shared_list = [
                '.btn',
                '.ui-btn',
                '.data-table th',
                '.data-table td',
                '.tokenbar',
                '.badge',
                '.table-card',
                '.nav-item',
            ]
            for sp in shared_list:
                # 检查行是否以共享 primitive 开头（无 .p- 前缀）
                if (
                    stripped.startswith(sp + ' ')
                    or stripped.startswith(sp + '{')
                    or stripped.startswith(sp + ',')
                ):
                    errors.append(f'[BLOCK] {rel} 在命名空间外定义了共享 primitive: {sp}')
                    break
    return errors


# 解析命令行参数并运行脚本入口。
def main() -> None:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    errors: list[str] = []

    print('=== UI Sort & Contract Quality Gate ===\n')

    # 检查 1: 页面脚本加载
    print('[1] 页面脚本加载检查...')
    e = check_page_scripts()
    errors.extend(e)
    print(f'    {"PASS" if not e else "FAIL"}: {len(e)} 个问题\n')

    # 检查 2: 排序按钮统一
    print('[2] 排序按钮唯一 contract 检查...')
    e = check_sort_unification()
    errors.extend(e)
    print(f'    {"PASS" if not e else "FAIL"}: {len(e)} 个问题\n')

    # 检查 3: 无重复 th rule
    print('[3] _tables.css 重复 th rule 检查...')
    e = check_no_duplicate_th_rules()
    errors.extend(e)
    print(f'    {"PASS" if not e else "FAIL"}: {len(e)} 个问题\n')

    # 检查 4: 脏 CSS 禁令
    print('[4] 脏 CSS 选择器禁令...')
    e = check_dirty_css_ban()
    errors.extend(e)
    print(f'    {"PASS" if not e else "FAIL"}: {len(e)} 个问题\n')

    if errors:
        print('=== 失败详情 ===')
        for e in errors:
            print(f'  {e}')
        sys.exit(1)
    else:
        print('[PASS] 所有 UI 排序与 contract 检查通过。')
        sys.exit(0)


if __name__ == '__main__':
    main()
