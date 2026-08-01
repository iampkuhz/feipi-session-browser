"""检查 Session Detail 模板接线与静态布局契约。

这些规则防止主内容宽度、hero 单列布局和 shell class 接线在无浏览器测试时悄然回退。唯一公开
入口是 `check(arguments)`；失败表示必需资源缺失或至少一项布局、标题、模板接线契约不成立。
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()


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
    """汇总稳定失败诊断和已观测的模板、selector 证据。"""

    failures: list[dict] = field(default_factory=list)
    observed: dict = field(default_factory=dict)

    def fail(self, code: str, message: str, next_inspection: list[str] | None = None) -> None:
        """追加带稳定 code 和后续排查建议的失败诊断。"""
        self.failures.append(
            {
                'code': code,
                'message': message,
                'nextInspection': next_inspection or [],
            }
        )

    def to_dict(self) -> dict:
        """生成供 Gate 消费的稳定结果结构。"""
        status = 'PASS' if not self.failures else 'FAIL'
        return {
            'schemaVersion': 1,
            'status': status,
            'gate': 'session-detail-static-css',
            'failures': self.failures,
            'observed': self.observed,
        }


def _check_phase1_hide_left_override(css: str, result: StaticCheckResult) -> None:
    """确认隐藏左栏时存在足够特异性的 Phase 1 grid 覆盖规则。"""
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


def _check_phase1_main_grid_column(css: str, result: StaticCheckResult) -> None:
    """确认 Phase 1 主内容区通过 grid 跨列或 flex 宽度契约铺满可用空间。"""
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


def _check_detail_width_contract(css: str, result: StaticCheckResult) -> None:
    """确认 Session Detail 容器显式声明 width 或 max-width。"""
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


def _is_two_column_grid(value: str) -> bool:
    """判断 grid-template-columns 值是否明确包含至少两列。"""
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


def _check_hero_main_single_column(
    css: str, result: None | StaticCheckResult = None
) -> StaticCheckResult:
    """确认 Session Detail hero 主区域没有继承或声明双列布局。"""
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

    # 没有页面级覆盖时必须检查基础规则，否则双列布局会被静默继承。
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


def _check_hero_title_wrapping(css: str, result: StaticCheckResult) -> None:
    """拒绝会在任意字符处断开 Session Detail 标题的换行规则。"""
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


def _check_session_shell_class_hook(session_text: str, result: StaticCheckResult) -> None:
    """确认 session.html 声明 shell_class block 及受支持的页面 shell class。"""
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


def _check_base_shell_class_application(base_text: str, result: StaticCheckResult) -> None:
    """确认 base.html 将 shell_class block 应用到 .shell 容器。"""
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


def _run_checks(
    css_path: Path, base_path: Path, session_path: Path, shell_css_path: Path | None = None
) -> dict:
    """读取静态资源并执行全部布局契约；任一必需文件缺失即返回失败。"""
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

    # 先合并规则实际可见的 CSS，再统一执行契约，避免各规则读取不同版本的输入。
    css = css_path.read_text()
    if shell_css_path is not None and shell_css_path.exists() and shell_css_path != css_path:
        css += '\n' + shell_css_path.read_text()
    if SESSION_DETAIL_CSS.exists():
        css += '\n' + SESSION_DETAIL_CSS.read_text()
    base_text = base_path.read_text()
    session_text = session_path.read_text()

    # 按布局、标题和模板接线三个阶段累积诊断，最后只归约一次状态。
    _check_phase1_hide_left_override(css, result)
    _check_phase1_main_grid_column(css, result)
    _check_detail_width_contract(css, result)
    _check_hero_main_single_column(css, result)
    _check_hero_title_wrapping(css, result)
    _check_session_shell_class_hook(session_text, result)
    _check_base_shell_class_application(base_text, result)

    return result.to_dict()


def _check_repository() -> list[str]:
    """对仓库默认资源执行检查并返回扁平诊断列表。"""
    result = _run_checks(SHELL_CSS_FILE, BASE_HTML, SESSION_HTML)
    return [f"{failure['code']}: {failure['message']}" for failure in result['failures']]


def check(arguments: list[str]) -> CheckResult:
    """解析统一 CLI 参数，并按布局、标题、模板接线的既定顺序返回失败。"""
    parser = argument_parser(description='检查 Session Detail 静态布局契约')
    parser.parse_args(arguments)
    return CheckResult.from_errors(_check_repository())
