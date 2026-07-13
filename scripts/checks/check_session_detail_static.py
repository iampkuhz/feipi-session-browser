#!/usr/bin/env python3
"""提供 检查 session detail static 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from scripts.checks._framework import repository_root

REPO_ROOT = repository_root()


CSS_FILE = (
    REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'css' / 'shell.css'
)
SHELL_CSS_FILE = (
    REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'css' / 'shell.css'
)
SESSION_DETAIL_CSS = (
    REPO_ROOT
    / 'java'
    / 'web'
    / 'src'
    / 'main'
    / 'resources'
    / 'static'
    / 'css'
    / 'session-detail.css'
)
BASE_HTML = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'templates' / 'base.html'
SESSION_HTML = (
    REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'templates' / 'session.html'
)
MIN_GRID_COLUMNS = 2


@dataclass
class StaticCheckResult:
    """汇总 StaticCheckResult 的检查结果。

    属性：
        failures: failures 参数。
        observed: observed 参数。
    """

    failures: list[dict] = field(default_factory=list)
    observed: dict = field(default_factory=dict)

    # 维护fail。
    def fail(self, code: str, message: str, next_inspection: list[str] | None = None) -> None:
        """参数：
        code: 稳定的machine-读取able 失败项 code。
        message: 诊断消息。
        next_inspection: 可选follow-up 文件 或 rules用于debugging。
        """
        self.failures.append(
            {
                'code': code,
                'message': message,
                'nextInspection': next_inspection or [],
            }
        )

    # 维护通过 检查。
    def pass_check(self) -> None:
        """执行 `pass_check` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        pass

    # 维护字典。
    def to_dict(self) -> dict:
        """返回：
        结果映射。
        """
        status = 'PASS' if not self.failures else 'FAIL'
        return {
            'schemaVersion': 1,
            'status': status,
            'gate': 'session-detail-static-css',
            'failures': self.failures,
            'observed': self.observed,
        }


# 检查 Phase 1 hide-left 覆盖规则。
def check_phase1_hide_left_override(css: str, result: StaticCheckResult) -> None:
    """参数：
    css: 待检查的 CSS 文本。
    result: Accumulator receiving observed selectors 或 失败项。
    """
    hide_left_phase1 = bool(
        re.search(
            r'body\.hide-left\s+\.shell\.(?:phase1-shell|no-inspector\.phase1-shell)',
            css,
        )
    )
    hide_left_noinspector = bool(
        re.search(
            r'body\.hide-left\s+\.shell\.no-inspector',
            css,
        )
    )
    has_grid_tmpl = 'grid-template-columns' in css
    if (hide_left_phase1 or hide_left_noinspector) and has_grid_tmpl:
        result.observed['phase1HideLeftOverride'] = True
    else:
        result.fail(
            'MISSING_PHASE1_HIDE_LEFT_OVERRIDE',
            'No high-specificity phase1 shell override for body.hide-left .shell.no-inspector.',
            [
                'Inspect shell.css for body.hide-left .shell.no-inspector override.',
                'Add body.hide-left .shell.no-inspector.phase1-shell override.',
            ],
        )


# 检查 Phase 1 主内容区 grid column。
def check_phase1_main_grid_column(css: str, result: StaticCheckResult) -> None:
    """参数：
        css: 待检查的 CSS 文本。
        result: Accumulator receiving observed selectors 或 失败项。

    说明：
        width: 100% + min-width: 0 (flex-based approach, 当前 默认)。
        当前 layout uses。main带width: 100% + min-width: 0用于full spanning。
    """
    has_main_rule = bool(re.search(r'\.shell\.phase1-shell\s+\.main', css))
    has_main_base = bool(re.search(r'\.main\b', css))  # 标记基础 main 规则是否存在
    has_grid_col = bool(re.search(r'grid-column:\s*1\s*/\s*-1', css))
    has_width_full = bool(re.search(r'width:\s*100%', css))
    has_min_width_zero = bool(re.search(r'min-width:\s*0', css))

    selectors = []
    if has_main_rule:
        selectors.append('.shell.phase1-shell .main')
    if has_main_base:
        selectors.append('.main (base)')
    if has_grid_col:
        selectors.append('grid-column: 1 / -1')
    if has_width_full:
        selectors.append('width: 100%')
    if has_min_width_zero:
        selectors.append('min-width: 0')
    result.observed['phase1MainRules'] = selectors

    spans_full = has_grid_col or (has_main_base and has_width_full and has_min_width_zero)
    if not spans_full:
        result.fail(
            'MISSING_PHASE1_MAIN_GRID_COLUMN',
            'Missing .main spanning full width.',
            [
                'Inspect shell.css for .main rule.',
                'Add width: 100% + min-width: 0 or grid-column: 1 / -1.',
            ],
        )


# 检查detail width 契约。
def check_detail_width_contract(css: str, result: StaticCheckResult) -> None:
    """参数：
    css: 待检查的 CSS 文本。
    result: 用于累积检查结果的可变对象。
    """
    has_detail = bool(re.search(r'\.session-detail-phase1', css))
    has_width = bool(
        re.search(
            r'\.session-detail-phase1[^}]*?(?:width|max-width)',
            css,
            re.DOTALL,
        )
    )
    if not has_width:
        has_width = bool(
            re.search(
                r'\.session-detail-phase1\s*\{[^}]*width',
                css,
                re.DOTALL,
            )
        )

    result.observed['detailWidthRule'] = has_detail and has_width

    if has_detail and not has_width:
        result.fail(
            'MISSING_SESSION_DETAIL_WIDTH_CONTRACT',
            '.session-detail-phase1 exists but lacks width/max-width rule.',
            [
                'Inspect shell.css for .session-detail-phase1 width rule.',
                'Add width: min(100%, 1360px) or max-width with margin: 0 auto.',
            ],
        )


# 判断是否two column grid。
def _is_two_column_grid(value: str) -> bool:
    """参数：
        value: value 参数。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    val = value.strip().rstrip(';').strip()
    if val in ('1fr', '100%', 'auto', 'none'):
        return False
    if re.match(r'repeat\s*\(\s*1\s*,', val):
        return False
    if re.match(r'repeat\s*\(\s*[2-9]\d*\s*,', val):
        return True
    depth = 0
    tokens: list[str] = []
    current = ''
    for ch in val:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif ch == ' ' and depth == 0:
            if current.strip():
                tokens.append(current.strip())
            current = ''
        else:
            current += ch
    if current.strip():
        tokens.append(current.strip())
    return len(tokens) >= MIN_GRID_COLUMNS


# 检查 hero 主区域保持单列。
def check_hero_main_single_column(
    css: str, result: None | StaticCheckResult = None
) -> StaticCheckResult:
    """参数：
        css: 待检查的 CSS 文本。
        result: 用于累积检查结果的可变对象。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    result = result or StaticCheckResult()

    scoped_blocks = re.findall(
        r'\.session-detail-phase1\s+\.hero-main\s*\{([^}]*)\}',
        css,
    )
    observed_rules = []
    for block in scoped_blocks:
        observed_rules.append(block.strip()[:120])
        col_match = re.search(r'grid-template-columns:\s*([^;]+)', block)
        if col_match and _is_two_column_grid(col_match.group(1)):
            result.fail(
                'HERO_MAIN_STILL_TWO_COLUMN',
                '.session-detail-phase1 .hero-main has a two-column grid-template-columns.',
                [
                    'Inspect shell.css for .session-detail-phase1 .hero-main.',
                    'Change to grid-template-columns: 1fr.',
                ],
            )

    if not scoped_blocks:
        base_blocks = re.findall(r'\.hero-main\s*\{([^}]*)\}', css)
        for block in base_blocks:
            col_match = re.search(r'grid-template-columns:\s*([^;]+)', block)
            if col_match and _is_two_column_grid(col_match.group(1)):
                result.fail(
                    'HERO_MAIN_STILL_TWO_COLUMN',
                    'No .session-detail-phase1 .hero-main override exists, and base '
                    '.hero-main is two-column.',
                    [
                        'Add .session-detail-phase1 .hero-main { grid-template-columns: 1fr; }.',
                    ],
                )
                break

    result.observed['heroMainRules'] = observed_rules
    return result


# 检查hero 标题 wrapping。
def check_hero_title_wrapping(css: str, result: StaticCheckResult) -> None:
    """参数：
    css: 待检查的 CSS 文本。
    result: 用于累积检查结果的可变对象。
    """
    title_blocks = re.findall(
        r'\.hero-title\s*\{([^}]*)\}',
        css,
    )
    for block in title_blocks:
        if re.search(r'overflow-wrap\s*:\s*anywhere', block):
            result.fail(
                'HERO_TITLE_UNSAFE_ANYWHERE_WRAP',
                '.hero-title uses overflow-wrap: anywhere — unsafe for long session titles.',
                [
                    'Inspect shell.css .hero-title overflow-wrap.',
                    'Use overflow-wrap: break-word or line-clamp instead.',
                ],
            )
        if re.search(r'word-break\s*:\s*break-all', block):
            result.fail(
                'HERO_TITLE_UNSAFE_ANYWHERE_WRAP',
                '.hero-title uses word-break: break-all — unsafe for long session titles.',
                [
                    'Inspect shell.css .hero-title word-break.',
                    'Use word-break: normal or overflow-wrap: break-word instead.',
                ],
            )


# 检查session shell class hook。
def check_session_shell_class_hook(session_text: str, result: StaticCheckResult) -> None:
    """参数：
    session_text: 待检查的文本。
    result: 用于累积检查结果的可变对象。
    """
    has_block = bool(re.search(r'\{%\s*block\s+shell_class\s*%\}', session_text))
    has_phase1 = 'phase1-shell' in session_text
    has_no_inspector = 'no-inspector' in session_text
    has_v9_shell = 'sd-shell' in session_text

    result.observed['sessionShellClassHook'] = {
        'hasBlock': has_block,
        'hasPhase1Shell': has_phase1,
        'hasNoInspector': has_no_inspector,
        'hasV9Shell': has_v9_shell,
    }

    if not has_block:
        result.fail(
            'MISSING_SESSION_SHELL_CLASS_HOOK',
            'session.html lacks {% block shell_class %} — shell class injection not possible.',
            [
                'Inspect session.html for {% block shell_class %}.',
                'Add {% block shell_class %} with phase1-shell no-inspector or sd-shell.',
            ],
        )
    elif not has_phase1 and not has_v9_shell:
        result.fail(
            'MISSING_SESSION_SHELL_CLASS_HOOK',
            'session.html shell_class block lacks phase1-shell or sd-shell.',
            [
                'Ensure session.html shell_class includes phase1-shell (or sd-shell).',
            ],
        )


# 检查基础 shell class 的应用位置。
def check_base_shell_class_application(base_text: str, result: StaticCheckResult) -> None:
    """参数：
    base_text: 待检查的文本。
    result: 用于累积检查结果的可变对象。
    """
    has_shell_with_block = bool(
        re.search(
            r'class="shell[^"]*\{%\s*block\s+shell_class',
            base_text,
        )
    )
    has_data_shell = 'data-session-detail-shell' in base_text

    result.observed['baseShellClassApplication'] = {
        'hasShellWithBlock': has_shell_with_block,
        'hasDataShellAttr': has_data_shell,
    }

    if not has_shell_with_block:
        result.fail(
            'MISSING_BASE_SHELL_CLASS_APPLICATION',
            'base.html does not apply {% block shell_class %} to .shell container.',
            [
                'Inspect base.html .shell element.',
                'Add {% block shell_class %}{% endblock %} inside .shell class attribute.',
            ],
        )


# 运行检查。
def run_checks(
    css_path: Path, base_path: Path, session_path: Path, shell_css_path: Path | None = None
) -> dict:
    """参数：
        css_path: CSS 文件路径。
        base_path: 待检查的路径。
        session_path: 待检查的路径。
        shell_css_path: 可选secondary shell CSS 路径用于compatibility。

    返回：
        结果映射。
    """
    result = StaticCheckResult()

    if not css_path.exists():
        result.fail('MISSING_CSS_FILE', f'CSS file not found: {css_path}')
        return result.to_dict()
    if not base_path.exists():
        result.fail('MISSING_BASE_HTML', f'base.html not found: {base_path}')
        return result.to_dict()
    if not session_path.exists():
        result.fail('MISSING_SESSION_HTML', f'session.html not found: {session_path}')
        return result.to_dict()

    # 读取primary CSS (shell.css)。
    css = css_path.read_text()
    if shell_css_path is not None and shell_css_path.exists() and shell_css_path != css_path:
        css += '\n' + shell_css_path.read_text()
    # 读取session-detail.css用于detail-specific rules。
    if SESSION_DETAIL_CSS.exists():
        css += '\n' + SESSION_DETAIL_CSS.read_text()
    base_text = base_path.read_text()
    session_text = session_path.read_text()

    check_phase1_hide_left_override(css, result)
    check_phase1_main_grid_column(css, result)
    check_detail_width_contract(css, result)
    check_hero_main_single_column(css, result)
    check_hero_title_wrapping(css, result)
    check_session_shell_class_hook(session_text, result)
    check_base_shell_class_application(base_text, result)

    return result.to_dict()


def check_repository() -> list[str]:
    """返回 repository Session Detail 静态契约诊断。"""
    result = run_checks(CSS_FILE, BASE_HTML, SESSION_HTML, SHELL_CSS_FILE)
    return [f"{failure['code']}: {failure['message']}" for failure in result['failures']]
