#!/usr/bin/env python3
"""Check UI density and font-size thresholds for compact mode.

Performs static analysis on style.css CSS variable tokens and selector
font-size declarations, verifying readability thresholds.

Usage:
    cd <repo-root>
    PYTHONPATH=src python scripts/check_ui_density_and_font_size.py

Exit codes:
    0 — all checks pass
    1 — one or more checks fail
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CSS_FILE = Path(__file__).resolve().parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"

# Typography token definitions expected in :root
TEXT_TOKENS = {
    "--text-micro":     {"value_px": None},
    "--text-xs":        {"value_px": None},
    "--text-sm":        {"value_px": None},
    "--text-base":      {"value_px": None},
    "--text-lg":        {"value_px": None},
    "--text-xl":        {"value_px": None},
    "--text-metric":    {"value_px": None},
    "--text-metric-sm": {"value_px": None},
}

# Threshold table: (selector_pattern, area_name, min_px, allowed_token)
# selector_pattern is a regex matched against the selector line.
# allowed_token is the minimum CSS --text-* token that is acceptable.
THRESHOLDS = [
    # Requirement 1: --text-base >= 14px
    ("__token__--text-base", "CSS variable --text-base", 14, "--text-lg"),

    # Requirement 2: Table body >= 13px
    (r"\.data-table\b", "Table body (.data-table)", 13, "--text-sm"),

    # Requirement 3: Timeline preview >= 14px
    (r"\.preview-cell\b", "Timeline preview (.preview-cell)", 14, "--text-lg"),

    # Requirement 4: Button text >= 13px
    (r"\.btn\b", "Button (.btn)", 13, "--text-sm"),

    # Requirement 5: Timestamp >= 12px (inherits from parent bar)
    (r"\.session-info-bar\b", "Timestamp bar (.session-info-bar)", 12, "--text-sm"),

    # Requirement 6 (bonus): metrics strip label readable
    (r"\.metrics-strip__label\b", "Metrics strip label", 12, "--text-sm"),

    # Requirement 6 (bonus): metrics strip value readable
    (r"\.metrics-strip__value\b", "Metrics strip value", 12, "--text-sm"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_px(value: str) -> float | None:
    """Parse a CSS value like '13px' or '10px' into a float."""
    m = re.match(r'^([0-9.]+)\s*px$', value.strip())
    if m:
        return float(m.group(1))
    return None


def parse_css_tokens(css_text: str) -> dict[str, dict]:
    """Extract CSS variable token definitions from :root block."""
    tokens: dict[str, dict] = {name: {"value_px": None} for name in TEXT_TOKENS}
    # Grab the :root { ... } block
    root_m = re.search(r':root\s*\{((?:[^{}]|\{[^{}]*\})*)\}', css_text)
    if not root_m:
        return tokens
    block = root_m.group(1)
    for name in tokens:
        m = re.search(re.escape(name) + r'\s*:\s*([^;]+);', block)
        if m:
            px = parse_px(m.group(1).strip())
            if px is not None:
                tokens[name]["value_px"] = px
    return tokens


def resolve_token_ref(value: str, tokens: dict[str, dict]) -> tuple[float | None, str]:
    """Resolve a font-size value that may contain var() references.

    Returns (resolved_px, description).
    Handles:
    - Plain '13px'
    - 'var(--text-base)'
    - 'var(--density-font-size, var(--text-xs))' (fallback chain)
    """
    value = value.strip()

    # Plain pixel value
    px = parse_px(value)
    if px is not None:
        return px, f"{px}px (literal)"

    # var(--token)
    m = re.match(r'^var\(\s*(--[a-zA-Z0-9_-]+)\s*\)$', value)
    if m:
        token_name = m.group(1)
        if token_name in tokens and tokens[token_name]["value_px"] is not None:
            px_val = tokens[token_name]["value_px"]
            return px_val, f"{px_val}px (via {token_name})"
        return None, f"unresolved: {value}"

    # var(--token, fallback) — extract fallback
    m = re.match(r'^var\(\s*--[a-zA-Z0-9_-]+\s*,\s*(.+?)\s*\)$', value)
    if m:
        fallback = m.group(1).strip()
        # Recurse into fallback
        return resolve_token_ref(fallback, tokens)

    return None, f"unresolved: {value}"


def extract_font_size_rules(css_text: str) -> list[dict]:
    """Extract {selector, property_value} pairs for font-size declarations.

    Uses a simple regex-based approach — not a full CSS parser.
    Handles both inline selectors and declarations inside blocks.
    """
    results = []

    # Strip CSS comments for cleaner parsing
    css_no_comments = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)

    # Pattern 1: inline selector { property: value; } — single-line
    # e.g. ".text-xs { font-size: var(--text-xs); }"
    inline_pat = re.compile(
        r'([^{@][^{]*?)\s*\{\s*font-size\s*:\s*([^;]+)\s*;\s*\}'
    )
    for m in inline_pat.finditer(css_no_comments):
        selector = m.group(1).strip()
        value = m.group(2).strip()
        # Skip @media, @keyframes, etc.
        if selector.startswith('@') or '/' in selector:
            continue
        # Clean up multi-line selectors
        selector = re.sub(r'\s+', ' ', selector).strip()
        if not selector or len(selector) > 200:
            continue
        results.append({"selector": selector, "value": value, "line": _line_number(css_text, m.start())})

    # Pattern 2: multi-line blocks — find font-size inside a rule block
    block_pat = re.compile(
        r'([^{@][^{]*?)\s*\{([^}]+)\}',
        re.MULTILINE
    )
    for m in block_pat.finditer(css_no_comments):
        selector = m.group(1).strip()
        block = m.group(2)
        fs_m = re.search(r'font-size\s*:\s*([^;]+);', block)
        if fs_m:
            value = fs_m.group(1).strip()
            # Avoid duplicates from inline pattern
            already = any(
                r["selector"] == selector and r["value"] == value
                for r in results
            )
            if not already:
                # Clean up multi-line selectors
                selector = re.sub(r'\s+', ' ', selector).strip()
                if not selector or len(selector) > 200:
                    continue
                results.append({"selector": selector, "value": value, "line": _line_number(css_text, m.start())})

    return results


def _line_number(text: str, pos: int) -> int:
    return text[:pos].count('\n') + 1


def _selector_matches(pattern: str, selector: str) -> bool:
    """Check if a regex pattern matches a CSS selector."""
    return bool(re.search(pattern, selector))


# ---------------------------------------------------------------------------
# Main check logic
# ---------------------------------------------------------------------------

def run_checks(css_path: Path) -> tuple[bool, list[str]]:
    """Run all density/font-size checks.

    Returns (all_pass, report_lines).
    """
    if not css_path.is_file():
        return False, [f"FAIL: CSS file not found: {css_path}"]

    css_text = css_path.read_text(encoding="utf-8")
    tokens = parse_css_tokens(css_text)
    rules = extract_font_size_rules(css_text)

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("UI Density & Font-Size Check (compact mode)")
    lines.append("=" * 72)
    lines.append("")

    # --- Section 1: Token summary ---
    lines.append("── CSS Token Values ──")
    for name, info in tokens.items():
        status = "OK" if info["value_px"] is not None else "??"
        val = f"{info['value_px']}px" if info["value_px"] is not None else "(unresolved)"
        lines.append(f"  [{status}] {name} = {val}")
    lines.append("")

    # --- Section 2: Threshold checks ---
    lines.append("── Threshold Checks ──")
    all_pass = True

    for pattern, area, min_px, min_token in THRESHOLDS:
        # Special case: direct token check (marked with __token__ prefix)
        if pattern.startswith("__token__"):
            token_name = pattern.replace("__token__", "")
            actual_px = tokens.get(token_name, {}).get("value_px")
            min_token_px = tokens.get(min_token, {}).get("value_px")
            if actual_px is None:
                lines.append(f"  [FAIL] {area}: {token_name} unresolved")
                all_pass = False
            elif min_token_px is not None and actual_px >= min_token_px:
                lines.append(f"  [OK]   {area}: {token_name} = {actual_px}px >= {min_px}px ({min_token}={min_token_px}px)")
            elif actual_px >= min_px:
                lines.append(f"  [OK]   {area}: {token_name} = {actual_px}px >= {min_px}px")
            else:
                lines.append(f"  [FAIL] {area}: {token_name} = {actual_px}px < {min_px}px (need >= {min_token}={min_token_px}px)")
                all_pass = False
            continue

        # Selector-based check
        matching = [r for r in rules if _selector_matches(pattern, r["selector"])]
        if not matching:
            lines.append(f"  [WARN] {area}: no font-size rule matching '{pattern}'")
            continue

        for rule in matching:
            px, desc = resolve_token_ref(rule["value"], tokens)
            if px is None:
                lines.append(f"  [WARN] {area} ({rule['selector']}): unresolved font-size '{rule['value']}' (line {rule['line']})")
                continue

            min_token_px = tokens.get(min_token, {}).get("value_px")
            min_token_label = min_token
            if min_token_px is not None:
                min_token_label = f"{min_token}={min_token_px}px"

            if px >= min_px:
                lines.append(f"  [OK]   {area}: {rule['selector']} = {desc} >= {min_px}px (threshold)")
            else:
                lines.append(f"  [FAIL] {area}: {rule['selector']} = {desc} < {min_px}px (need >= {min_token_label})")
                all_pass = False

    lines.append("")

    # --- Section 3: All font-size declarations using text-micro or text-xs ---
    lines.append("── Potentially Too-Small Declarations (text-micro / text-xs) ──")
    tiny_rules = [
        r for r in rules
        if "text-micro" in r["value"] or "text-xs" in r["value"]
    ]
    # Sort by selector for readability
    tiny_rules.sort(key=lambda r: r["selector"])

    # Show first 30 as a sample
    shown = 0
    for rule in tiny_rules:
        px, desc = resolve_token_ref(rule["value"], tokens)
        px_label = f"{px}px" if px is not None else "??"
        lines.append(f"  line {rule['line']:>4}: {rule['selector'][:60]:<60} -> {desc}")
        shown += 1
        if shown >= 50:
            remaining = len(tiny_rules) - shown
            if remaining > 0:
                lines.append(f"  ... and {remaining} more")
            break

    if not tiny_rules:
        lines.append("  (none found)")

    lines.append("")
    lines.append("=" * 72)
    if all_pass:
        lines.append("RESULT: ALL CHECKS PASSED")
    else:
        lines.append("RESULT: SOME CHECKS FAILED — review FAIL items above")
    lines.append("=" * 72)

    return all_pass, lines


def main() -> None:
    css_path = CSS_FILE
    if len(sys.argv) > 1:
        css_path = Path(sys.argv[1])

    all_pass, report = run_checks(css_path)
    for line in report:
        print(line)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
