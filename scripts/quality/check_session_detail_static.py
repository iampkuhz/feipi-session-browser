#!/usr/bin/env python3
"""Static CSS + template contract check for session detail Phase 1 layout.

Verifies that style.css and templates contain rules sufficient to prevent
the cascade conflict where body.hide-left .shell.no-inspector overrides
.shell.phase1-shell, causing .main to fall into a 0px grid column.

Checks:
  1. phase1 shell hide-left override
  2. phase1 main grid-column: 1 / -1
  3. session detail width contract
  4. hero main single column (not two-column)
  5. hero title wrapping safety (no overflow-wrap:anywhere)
  6. session.html shell_class hook
  7. base.html shell_class application

Usage:
    python3 scripts/quality/check_session_detail_static.py
    python3 scripts/quality/check_session_detail_static.py --self-test
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CSS_FILE = REPO_ROOT / "src" / "session_browser" / "web" / "static" / "style.css"
SHELL_CSS_FILE = REPO_ROOT / "src" / "session_browser" / "web" / "static" / "css" / "shell.css"
BASE_HTML = REPO_ROOT / "src" / "session_browser" / "web" / "templates" / "base.html"
SESSION_HTML = REPO_ROOT / "src" / "session_browser" / "web" / "templates" / "session.html"


class StaticCheckResult:
    def __init__(self):
        self.failures: list[dict] = []
        self.observed: dict = {}

    def fail(self, code: str, message: str, next_inspection: list[str] | None = None):
        self.failures.append({
            "code": code,
            "message": message,
            "nextInspection": next_inspection or [],
        })

    def pass_check(self):
        pass

    def to_dict(self) -> dict:
        status = "PASS" if not self.failures else "FAIL"
        return {
            "status": status,
            "gate": "session-detail-static-css",
            "failures": self.failures,
            "observed": self.observed,
        }


def check_phase1_hide_left_override(css: str, result: StaticCheckResult):
    """Check 1: High-specificity body.hide-left override for phase1 shell."""
    # Need: body.hide-left .shell.no-inspector or body.hide-left .shell.phase1-shell
    # with grid-template-columns and minmax(0, 1fr)
    hide_left_phase1 = bool(re.search(
        r'body\.hide-left\s+\.shell\.(?:phase1-shell|no-inspector\.phase1-shell)',
        css,
    ))
    hide_left_noinspector = bool(re.search(
        r'body\.hide-left\s+\.shell\.no-inspector',
        css,
    ))
    has_grid_tmpl = "grid-template-columns" in css
    has_minmax = "minmax(0, 1fr)" in css

    if (hide_left_phase1 or hide_left_noinspector) and has_grid_tmpl:
        result.observed["phase1HideLeftOverride"] = True
    else:
        result.fail(
            "MISSING_PHASE1_HIDE_LEFT_OVERRIDE",
            "No high-specificity phase1 shell override for body.hide-left .shell.no-inspector.",
            [
                "Inspect style.css around shell/no-inspector/hide-left rules.",
                "Add body.hide-left .shell.no-inspector.phase1-shell override.",
            ],
        )


def check_phase1_main_grid_column(css: str, result: StaticCheckResult):
    """Check 2: .shell.phase1-shell .main must have grid-column: 1 / -1."""
    has_main_rule = bool(re.search(r'\.shell\.phase1-shell\s+\.main', css))
    has_grid_col = bool(re.search(r'grid-column:\s*1\s*/\s*-1', css))
    has_width_full = bool(re.search(r'width:\s*100%', css))
    has_min_width_zero = bool(re.search(r'min-width:\s*0', css))

    selectors = []
    if has_main_rule:
        selectors.append(".shell.phase1-shell .main")
    if has_grid_col:
        selectors.append("grid-column: 1 / -1")
    if has_width_full:
        selectors.append("width: 100%")
    if has_min_width_zero:
        selectors.append("min-width: 0")
    result.observed["phase1MainRules"] = selectors

    if not has_main_rule or not has_grid_col:
        result.fail(
            "MISSING_PHASE1_MAIN_GRID_COLUMN",
            "Missing .shell.phase1-shell .main with grid-column: 1 / -1.",
            [
                "Inspect style.css for .shell.phase1-shell .main rule.",
                "Add grid-column: 1 / -1, width: 100%, min-width: 0.",
            ],
        )


def check_detail_width_contract(css: str, result: StaticCheckResult):
    """Check 3: .session-detail-phase1 must have width contract."""
    # Look for session-detail-phase1 with width/max-width
    has_detail = bool(re.search(r'\.session-detail-phase1', css))
    has_width = bool(re.search(
        r'\.session-detail-phase1[^}]*?(?:width|max-width)',
        css,
        re.DOTALL,
    ))
    # Also accept width within a block near session-detail-phase1
    if not has_width:
        has_width = bool(re.search(
            r'\.session-detail-phase1\s*\{[^}]*width',
            css,
            re.DOTALL,
        ))

    result.observed["detailWidthRule"] = has_detail and has_width

    if has_detail and not has_width:
        result.fail(
            "MISSING_SESSION_DETAIL_WIDTH_CONTRACT",
            ".session-detail-phase1 exists but lacks width/max-width rule.",
            [
                "Inspect style.css for .session-detail-phase1 width rule.",
                "Add width: min(100%, 1360px) or max-width with margin: 0 auto.",
            ],
        )


def _is_two_column_grid(value: str) -> bool:
    """Check if a grid-template-columns value defines two columns."""
    val = value.strip().rstrip(";").strip()
    # Single column patterns
    if val in ("1fr", "100%", "auto", "none"):
        return False
    # repeat(1, ...) is single
    if re.match(r'repeat\s*\(\s*1\s*,', val):
        return False
    # repeat(N, ...) with N > 1 is multi
    if re.match(r'repeat\s*\(\s*[2-9]\d*\s*,', val):
        return True
    # Two+ space-separated values (not inside parens) = multi-column
    # Split by spaces but respect function call nesting
    depth = 0
    tokens: list[str] = []
    current = ""
    for ch in val:
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch == " " and depth == 0:
            if current.strip():
                tokens.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        tokens.append(current.strip())
    return len(tokens) >= 2


def check_hero_main_single_column(css: str, result: None | StaticCheckResult = None):
    """Check 4: .session-detail-phase1 .hero-main must NOT be two-column."""
    result = result or StaticCheckResult()

    # Check .session-detail-phase1 .hero-main specifically
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
                "HERO_MAIN_STILL_TWO_COLUMN",
                ".session-detail-phase1 .hero-main has a two-column grid-template-columns.",
                [
                    "Inspect style.css for .session-detail-phase1 .hero-main.",
                    "Change to grid-template-columns: 1fr.",
                ],
            )

    # Also check: if no .session-detail-phase1 .hero-main rule exists at all,
    # but base .hero-main is two-column, that's a risk
    if not scoped_blocks:
        base_blocks = re.findall(r'\.hero-main\s*\{([^}]*)\}', css)
        for block in base_blocks:
            col_match = re.search(r'grid-template-columns:\s*([^;]+)', block)
            if col_match and _is_two_column_grid(col_match.group(1)):
                result.fail(
                    "HERO_MAIN_STILL_TWO_COLUMN",
                    "No .session-detail-phase1 .hero-main override exists, and base "
                    ".hero-main is two-column.",
                    [
                        "Add .session-detail-phase1 .hero-main { grid-template-columns: 1fr; }.",
                    ],
                )
                break

    result.observed["heroMainRules"] = observed_rules
    return result


def check_hero_title_wrapping(css: str, result: StaticCheckResult):
    """Check 5: hero-title must NOT use overflow-wrap:anywhere or word-break:break-all."""
    title_blocks = re.findall(
        r'\.hero-title\s*\{([^}]*)\}',
        css,
    )
    for block in title_blocks:
        if re.search(r'overflow-wrap\s*:\s*anywhere', block):
            result.fail(
                "HERO_TITLE_UNSAFE_ANYWHERE_WRAP",
                ".hero-title uses overflow-wrap: anywhere — unsafe for long session titles.",
                [
                    "Inspect style.css .hero-title overflow-wrap.",
                    "Use overflow-wrap: break-word or line-clamp instead.",
                ],
            )
        if re.search(r'word-break\s*:\s*break-all', block):
            result.fail(
                "HERO_TITLE_UNSAFE_ANYWHERE_WRAP",
                ".hero-title uses word-break: break-all — unsafe for long session titles.",
                [
                    "Inspect style.css .hero-title word-break.",
                    "Use word-break: normal or overflow-wrap: break-word instead.",
                ],
            )


def check_session_shell_class_hook(session_text: str, result: StaticCheckResult):
    """Check 6: session.html must declare shell_class block with appropriate classes.

    Accepts either:
    - Phase 1: phase1-shell + no-inspector
    - v9: sd-shell (with session-detail-page or similar)
    """
    has_block = bool(re.search(r'\{%\s*block\s+shell_class\s*%\}', session_text))
    has_phase1 = "phase1-shell" in session_text
    has_no_inspector = "no-inspector" in session_text
    has_v9_shell = "sd-shell" in session_text

    result.observed["sessionShellClassHook"] = {
        "hasBlock": has_block,
        "hasPhase1Shell": has_phase1,
        "hasNoInspector": has_no_inspector,
        "hasV9Shell": has_v9_shell,
    }

    if not has_block:
        result.fail(
            "MISSING_SESSION_SHELL_CLASS_HOOK",
            "session.html lacks {% block shell_class %} — shell class injection not possible.",
            [
                "Inspect session.html for {% block shell_class %}.",
                "Add {% block shell_class %} with phase1-shell no-inspector or sd-shell.",
            ],
        )
    elif not has_phase1 and not has_v9_shell:
        result.fail(
            "MISSING_SESSION_SHELL_CLASS_HOOK",
            "session.html shell_class block lacks phase1-shell or sd-shell.",
            [
                "Ensure session.html shell_class includes phase1-shell (or sd-shell for v9).",
            ],
        )


def check_base_shell_class_application(base_text: str, result: StaticCheckResult):
    """Check 7: base.html must apply shell_class to .shell container."""
    # Check: .shell container uses shell_class block
    has_shell_with_block = bool(re.search(
        r'class="shell[^"]*\{%\s*block\s+shell_class',
        base_text,
    ))
    has_data_shell = "data-session-detail-shell" in base_text

    result.observed["baseShellClassApplication"] = {
        "hasShellWithBlock": has_shell_with_block,
        "hasDataShellAttr": has_data_shell,
    }

    if not has_shell_with_block:
        result.fail(
            "MISSING_BASE_SHELL_CLASS_APPLICATION",
            "base.html does not apply {% block shell_class %} to .shell container.",
            [
                "Inspect base.html .shell element.",
                "Add {% block shell_class %}{% endblock %} inside .shell class attribute.",
            ],
        )


def run_checks(css_path: Path, base_path: Path, session_path: Path,
               shell_css_path: Path | None = None) -> dict:
    """Run all static checks and return result dict."""
    result = StaticCheckResult()

    if not css_path.exists():
        result.fail("MISSING_CSS_FILE", f"CSS file not found: {css_path}")
        return result.to_dict()
    if not base_path.exists():
        result.fail("MISSING_BASE_HTML", f"base.html not found: {base_path}")
        return result.to_dict()
    if not session_path.exists():
        result.fail("MISSING_SESSION_HTML", f"session.html not found: {session_path}")
        return result.to_dict()

    css = css_path.read_text()
    # Also read shell.css if available (shell rules migrated there in Task 05)
    if shell_css_path is not None and shell_css_path.exists():
        css += "\n" + shell_css_path.read_text()
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


def main():
    if "--self-test" in sys.argv:
        return _self_test()

    out = run_checks(CSS_FILE, BASE_HTML, SESSION_HTML, SHELL_CSS_FILE)
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if out["status"] == "FAIL":
        for f in out["failures"]:
            print(f"  FAIL: [{f['code']}] {f['message']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("PASS: All static CSS/template checks passed")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    """Run self-tests using temporary CSS/HTML fixtures."""
    import tempfile

    GOOD_CSS = """
body.hide-left .shell.phase1-shell { grid-template-columns: 0 minmax(0, 1fr); }
.shell.phase1-shell .main {
    grid-column: 1 / -1;
    width: 100%;
    min-width: 0;
}
.session-detail-phase1 { width: min(100%, 1360px); margin: 0 auto; }
.hero-main { grid-template-columns: 1fr; }
.hero-title { overflow-wrap: break-word; word-break: normal; }
"""

    GOOD_BASE = """
<div class="shell{% block shell_class %}{% endblock %}" data-session-detail-shell>
"""

    GOOD_SESSION = """
{% extends "base.html" %}
{% block shell_class %} no-inspector phase1-shell{% endblock %}
"""

    def _run(name, css_text, base_text, session_text, expect_pass):
        with tempfile.TemporaryDirectory() as td:
            css_p = Path(td) / "style.css"
            base_p = Path(td) / "base.html"
            session_p = Path(td) / "session.html"
            css_p.write_text(css_text)
            base_p.write_text(base_text)
            session_p.write_text(session_text)
            out = run_checks(css_p, base_p, session_p)
            actual_pass = out["status"] == "PASS"
            if actual_pass == expect_pass:
                print(f"  PASS: {name}")
                return True
            else:
                codes = [f["code"] for f in out.get("failures", [])]
                print(f"  FAIL: {name} — expected {'PASS' if expect_pass else 'FAIL'}, got {out['status']}, failures: {codes}")
                return False

    failures = 0

    # 1. Full contract => PASS
    if not _run("full contract => PASS", GOOD_CSS, GOOD_BASE, GOOD_SESSION, True):
        failures += 1

    # 2. Missing hide-left override => FAIL
    bad_css_2 = """
.shell.phase1-shell .main { grid-column: 1 / -1; width: 100%; }
.session-detail-phase1 { width: 100%; }
.hero-main { grid-template-columns: 1fr; }
.hero-title { overflow-wrap: break-word; }
"""
    if not _run("missing hide-left override => FAIL", bad_css_2, GOOD_BASE, GOOD_SESSION, False):
        failures += 1

    # 3. Missing main grid-column => FAIL
    bad_css_3 = """
body.hide-left .shell.phase1-shell { grid-template-columns: 0 minmax(0, 1fr); }
.shell.phase1-shell .main { width: 100%; }
.session-detail-phase1 { width: 100%; }
.hero-main { grid-template-columns: 1fr; }
.hero-title { overflow-wrap: break-word; }
"""
    if not _run("missing main grid-column => FAIL", bad_css_3, GOOD_BASE, GOOD_SESSION, False):
        failures += 1

    # 4. Hero two-column => FAIL (scoped to .session-detail-phase1)
    bad_css_4 = GOOD_CSS.replace(
        ".hero-main { grid-template-columns: 1fr; }",
        ".session-detail-phase1 .hero-main { grid-template-columns: minmax(0, 1fr) minmax(360px, 520px); }",
    )
    if not _run("hero two-column => FAIL", bad_css_4, GOOD_BASE, GOOD_SESSION, False):
        failures += 1

    # 5. Hero title overflow-wrap:anywhere => FAIL
    bad_css_5 = GOOD_CSS.replace(
        ".hero-title { overflow-wrap: break-word; word-break: normal; }",
        ".hero-title { overflow-wrap: anywhere; }",
    )
    if not _run("hero title overflow-wrap:anywhere => FAIL", bad_css_5, GOOD_BASE, GOOD_SESSION, False):
        failures += 1

    # 6. Missing session shell_class hook => FAIL
    bad_session = """
{% extends "base.html" %}
"""
    if not _run("missing session shell_class => FAIL", GOOD_CSS, GOOD_BASE, bad_session, False):
        failures += 1

    # 7. Missing base shell class application => FAIL
    bad_base = """
<div class="shell" data-session-detail-shell>
"""
    if not _run("missing base shell application => FAIL", GOOD_CSS, bad_base, GOOD_SESSION, False):
        failures += 1

    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    else:
        print(f"\nAll self-tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
