#!/usr/bin/env python3
"""Validate CSS ownership rules for feipi-session-browser.

Checks:
  1. Shell selector violations in Layer 3/4 files
  2. Forbidden CSS filenames (versioned, patch, fix, overlay)
  3. style.css bloat (page-specific selectors in Layer 1)
  4. Duplicate selectors across files (excluding allowed additive overrides)

Usage:
    python3 scripts/validate_css_ownership.py [--verbose]

Exit code 0 = PASS, 1 = FAIL.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent / "src" / "session_browser" / "web" / "static"

# Shell selectors that MUST only be defined in style.css
SHELL_SELECTORS = {
    ".shell", ".app-shell", ".sidebar", ".topbar", ".content", ".footer",
    ".breadcrumb", ".topbar-breadcrumb", ".topbar-actions",
    ".main-panel", ".main", ".sd-shell", ".sd-content",
}

# Layout properties that indicate a shell override (not just additive)
LAYOUT_PROPERTIES = {
    "display", "grid-template-columns", "grid-template-rows", "grid-template",
    "padding-top", "padding-right", "padding-bottom", "padding-left", "padding",
    "min-height", "max-height", "height",
    "min-width", "max-width", "width",
    "margin-top", "margin-right", "margin-bottom", "margin-left", "margin",
    "gap", "row-gap", "column-gap",
    "align-items", "justify-content", "align-content", "align-self",
    "position", "top", "left", "bottom",
    "flex-direction", "flex-wrap", "flex-basis", "flex-grow", "flex-shrink", "flex",
    "overflow-x", "overflow-y", "overflow",
    "z-index",
}

# Selectors where additive (color/font/background only) is allowed in Layer 3
SHELL_SELECTORS_ADDITIVE = {
    ".topbar-breadcrumb",
    ".sidebar",       # legacy: background, border-right (additive)
    ".main",          # legacy: min-width (additive)
    ".sd-shell",      # legacy: background var; session-detail: CSS variables only
}

# Page-specific selectors that should NOT appear in style.css
PAGE_SPECIFIC_SELECTORS = [
    ".chart-card", ".chart-group", ".chart-group__stack", ".segment",
    ".legend-row", ".legend-item", ".legend-dot",
    ".page-head", ".scope-switch",
    ".sessions-page", ".token-cell", ".token-total", ".tokenbar-seg",
    ".sessions-filter-card", ".sessions-control-row",
    ".sd-hero", ".sd-tabs", ".trace-table", ".trace-round",
    ".hero-metrics", ".project-cell", ".project-name", ".project-tooltip",
    ".agent-cell", ".agent-main", ".efficiency",
    ".glossary-table", ".term-cell", ".formula-cell", ".sample-cell",
    ".state-panel", ".error-icon", ".error-title", ".error-description",
    ".metric-grid--glossary",
    ".legend-card", ".note-strip",
    ".ui-stat-pill", ".ui-search",
]

# Forbidden filename patterns
FORBIDDEN_PATTERNS = [
    re.compile(r"-v\d+\.css$"),      # dashboard-v16.css
    re.compile(r"-patch\.css$"),      # session-patch.css
    re.compile(r"-fix\.css$"),        # something-fix.css
    re.compile(r"-overlay\.css$"),    # something-overlay.css
    re.compile(r"-reference\.css$"),  # something-reference.css
]

# Known legitimate Layer 3/4 files (allowed to exist)
KNOWN_CSS = {
    "css/legacy-aliases.css",
    "css/dashboard.css",
    "css/sessions-list.css",
    "css/session-detail.css",
    "css/session-detail-timeline.css",  # deprecated, flagged separately
    "css/projects.css",
    "css/agents.css",
    "css/glossary.css",
    "css/states.css",
    "css/ui-primitives.css",
}

# ── Helpers ────────────────────────────────────────────────────────────────


def extract_selectors(css_path: Path) -> set[str]:
    """Extract top-level CSS selectors from a file."""
    selectors = set()
    try:
        text = css_path.read_text()
    except Exception:
        return selectors

    # Remove CSS comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # Match selectors before { — handles comma-separated groups
    for match in re.finditer(r'([^{}]+?)\s*\{', text):
        group = match.group(1).strip()
        # Skip @-rules
        if group.startswith("@") or not group:
            continue
        # Split comma-separated selectors
        for sel in group.split(","):
            sel = sel.strip()
            if not sel or sel.startswith("@"):
                continue
            # Extract the base selector (first class/element name)
            parts = sel.split()
            if parts:
                full = parts[0].split(":")[0].split("[")[0]
                if full.startswith((".", "#")):
                    selectors.add(full)
    return selectors


def has_shell_selector(css_path: Path) -> list[tuple[str, str]]:
    """Find shell selector definitions with layout properties in a file.

    Only flags violations where a shell selector is the **target** of the rule
    (e.g. `.topbar { ... }`), not a descendant parent (e.g. `.sd-shell .child`).
    Additive-only supplements (color, font, background) on allowed selectors
    are not flagged.
    """
    violations = []
    try:
        text = css_path.read_text()
    except Exception:
        return violations

    # Remove comments for analysis
    clean = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # Find all rule blocks
    pos = 0
    while True:
        m = re.search(r'([^{}]+?)\s*\{([^{}]*)\}', clean[pos:])
        if not m:
            break

        selector_text = m.group(1).strip()
        rule_body = m.group(2).strip()
        abs_pos = pos + m.start()

        # Count line number
        line_num = clean[:abs_pos].count('\n') + 1

        # Split comma-separated selectors
        selectors = [s.strip() for s in selector_text.split(",") if s.strip()]

        for sel_full in selectors:
            # A target shell selector is one where the selector is ONLY the
            # shell class (possibly with a modifier like .no-inspector),
            # NOT a descendant chain like ".sd-shell .child".
            # e.g. ".topbar" → target (1 part)
            # e.g. ".shell.no-inspector" → target (1 part, modifier on same class)
            # e.g. ".sd-shell .child" → NOT target (2+ parts, descendant)
            parts = sel_full.split()
            if len(parts) > 1:
                continue  # Descendant selector — skip
            if not parts:
                continue
            first_part = parts[0].split(":")[0].split("[")[0]

            if first_part not in SHELL_SELECTORS:
                continue

            # Check if this is an allowed additive selector
            if first_part in SHELL_SELECTORS_ADDITIVE:
                # Check if it defines layout properties
                has_layout = any(
                    re.search(rf'\b{re.escape(prop)}\s*:', rule_body)
                    for prop in LAYOUT_PROPERTIES
                )
                if not has_layout:
                    continue

            # This is a violation
            preview = rule_body[:80].replace('\n', ' ').strip()
            violations.append((first_part, f"line {line_num}: {sel_full} {{ {preview} ... }}"))

        pos = abs_pos + m.end() - m.start()

    return violations


def check_bloat(css_path: Path) -> list[tuple[str, str]]:
    """Find page-specific selectors in style.css."""
    violations = []
    try:
        text = css_path.read_text()
    except Exception:
        return violations

    for sel in PAGE_SPECIFIC_SELECTORS:
        # Use word boundary to avoid false positives
        pattern = re.compile(
            r'(?:^|[\s,;{}])' + re.escape(sel) + r'(?:\.[\w-]+|::?\w+|\[.*?\])?\s*\{',
            re.MULTILINE
        )
        matches = pattern.findall(text)
        if matches:
            violations.append((sel, f"found {len(matches)} occurrence(s)"))
    return violations


def check_forbidden_names(css_dir: Path) -> list[tuple[str, str]]:
    """Find CSS files matching forbidden naming patterns."""
    violations = []
    for f in sorted(css_dir.rglob("*.css")):
        rel = str(f.relative_to(css_dir))
        if f.name in ("style.css", "ui-primitives.css", "legacy-aliases.css"):
            continue
        if str(f.relative_to(css_dir)) in KNOWN_CSS:
            # Check if deprecated files should be flagged
            if str(f.relative_to(css_dir)) == "css/session-detail-timeline.css":
                violations.append((rel, "deprecated — should be merged and removed"))
            continue
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(f.name):
                violations.append((rel, f"forbidden filename pattern: {pat.pattern}"))
                break
    return violations


def check_duplicates(css_dir: Path, verbose: bool = False) -> list[tuple[str, str]]:
    """Find selectors defined in multiple files (excluding allowed cases)."""
    violations = []
    selector_map: dict[str, list[str]] = {}

    css_files = sorted(css_dir.rglob("*.css"))
    for f in css_files:
        rel = str(f.relative_to(css_dir))
        if f.name == "style.css":
            continue  # Layer 1 is the authority
        if rel == "css/session-detail-timeline.css":
            continue  # Deprecated, already flagged by forbidden_filename
        sels = extract_selectors(f)
        for sel in sels:
            if sel not in selector_map:
                selector_map[sel] = []
            selector_map[sel].append(rel)

    for sel, files in sorted(selector_map.items()):
        if len(files) > 1:
            # Check if this is a shell selector (should only be in style.css)
            base = sel.split(":")[0].split("[")[0]
            if base in SHELL_SELECTORS:
                # Exception: shell selectors used only for CSS variable scoping
                # (e.g. .sd-shell { --sd-bg: ... }) are allowed in multiple files
                # because they don't define layout — just token namespaces.
                all_var_only = True
                for f in files:
                    full_path = css_dir / f
                    try:
                        text = re.sub(r'/\*.*?\*/', '', full_path.read_text(), flags=re.DOTALL)
                    except Exception:
                        all_var_only = False
                        break
                    # Find all rules and check if `sel` appears as a target selector.
                    rule_pattern = re.compile(r'([^{}]+?)\s*\{([^}]*)\}')
                    found_target = False
                    for m in rule_pattern.finditer(text):
                        sel_text = m.group(1).strip()
                        body = m.group(2)
                        # Check each comma-separated sub-selector
                        for sub in sel_text.split(','):
                            sub = sub.strip()
                            parts = sub.split()
                            if not parts:
                                continue
                            # Only match exact target selectors, not descendants
                            if len(parts) > 1:
                                continue
                            first = parts[0].split(':')[0].split('[')[0]
                            if first == sel:
                                # This is a target rule for the shell selector
                                # Strip CSS variable definitions (--name: value),
                                # variable usages (var(--name) → VAR), and
                                # properties whose value is purely VAR.
                                stripped = re.sub(r'--[\w-]+\s*:[^;]*;', '', body)
                                stripped = re.sub(r'var\([^)]*\)', 'VAR', stripped)
                                stripped = re.sub(r'[\w-]+\s*:\s*VAR\s*;?', '', stripped)
                                has_non_var = bool(stripped.strip())
                                if has_non_var:
                                    all_var_only = False
                                else:
                                    found_target = True
                                break
                        if not all_var_only:
                            break
                    if not found_target:
                        all_var_only = False
                        break
                if all_var_only:
                    continue  # CSS variable scoping only, allowed
                violations.append((
                    sel,
                    f"defined in {len(files)} files: {', '.join(files)} "
                    f"(shell selectors must be in style.css only)"
                ))
            elif verbose:
                # Non-shell duplicates: info only, not a violation
                if verbose:
                    violations.append((
                        sel,
                        f"[INFO] defined in {len(files)} files: {', '.join(files)}"
                    ))
    return violations


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Validate CSS ownership rules")
    parser.add_argument("--verbose", action="store_true", help="Show info-level duplicates")
    args = parser.parse_args()

    violations = []

    # 1. Check shell selector violations in Layer 3/4 files
    layer34_files = [
        ROOT / "css/legacy-aliases.css",
        ROOT / "css/dashboard.css",
        ROOT / "css/sessions-list.css",
        ROOT / "css/session-detail.css",
        ROOT / "css/projects.css",
        ROOT / "css/agents.css",
        ROOT / "css/glossary.css",
        ROOT / "css/states.css",
    ]
    for f in layer34_files:
        if not f.exists():
            continue
        rel = str(f.relative_to(ROOT))
        v = has_shell_selector(f)
        for sel, ctx in v:
            violations.append(("shell_selector_violation", rel, f"{sel} — {ctx}"))

    # 2. Check forbidden filenames
    for name, ctx in check_forbidden_names(ROOT):
        violations.append(("forbidden_filename", name, ctx))

    # 3. Check style.css bloat
    style_css = ROOT / "style.css"
    if style_css.exists():
        for sel, ctx in check_bloat(style_css):
            violations.append(("style_bloat", "style.css", f"{sel} — {ctx}"))

    # 4. Check duplicate selectors
    for sel, ctx in check_duplicates(ROOT, verbose=args.verbose):
        if "[INFO]" in ctx:
            continue  # Info only, skip in non-verbose mode
        violations.append(("duplicate_selector", "multiple", f"{sel} — {ctx}"))

    # ── Report ─────────────────────────────────────────────────────────
    if violations:
        print(f"\n{'='*60}")
        print(f"CSS Ownership Validation — FAIL")
        print(f"{'='*60}")

        by_type: dict[str, list] = {}
        for vtype, file, detail in violations:
            by_type.setdefault(vtype, []).append((file, detail))

        for vtype, items in sorted(by_type.items()):
            print(f"\n--- {vtype} ({len(items)} issue(s)) ---")
            for file, detail in items:
                print(f"  [{file}] {detail}")

        print(f"\n{'='*60}")
        print(f"Total: {len(violations)} violation(s)")
        print(f"{'='*60}\n")
        return 1
    else:
        print(f"\n{'='*60}")
        print(f"CSS Ownership Validation — PASS")
        print(f"{'='*60}")
        print(f"No violations found.\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
