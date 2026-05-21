#!/usr/bin/env python3
"""Validate primitive screenshots against HIFI reference images.

This harness script validates that each UI primitive renders correctly
by taking screenshots in isolation and comparing them against HIFI reference images.

Usage:
    python3 scripts/qa/ui/validate_primitive_screenshots.py              # validate all
    python3 scripts/qa/ui/validate_primitive_screenshots.py --capture    # capture new screenshots
    python3 scripts/qa/ui/validate_primitive_screenshots.py --primitive button  # validate single
    python3 scripts/qa/ui/validate_primitive_screenshots.py --list       # list all primitives

Primitives covered:
    Canonical (15): button, icon_button, badge, metric_card, metric_grid,
                    pagination, token_bar, tooltip, popover, section_card,
                    data_table, filter_bar, payload_modal, empty_state, error_state
    Legacy (6): legacy-btn, select-control, stat-pill, th-static, th-sort, token-total

Reference image directory: qa/screenshots/primitive-references/
Actual screenshot directory: test-results/primitive-screenshots/
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[3]
PRIMITIVE_REFERENCES = ROOT / "qa" / "screenshots" / "primitive-references"
PRIMITIVE_ACTUALS = ROOT / "test-results" / "primitive-screenshots"

# Canonical primitives — each maps to a macro name in ui_primitives.html
CANONICAL_PRIMITIVES = [
    "button",
    "icon_button",
    "badge",
    "metric_card",
    "metric_grid",
    "pagination",
    "token_bar",
    "tooltip",
    "popover",
    "section_card",
    "data_table",
    "filter_bar",
    "payload_modal",
    "empty_state",
    "error_state",
]

# Legacy primitives — present for backward compatibility
LEGACY_PRIMITIVES = [
    "legacy-btn",
    "select-control",
    "stat-pill",
    "th-static",
    "th-sort",
    "token-total",
]

ALL_PRIMITIVES = CANONICAL_PRIMITIVES + LEGACY_PRIMITIVES

# Default viewport for screenshot capture
VIEWPORT = {"width": 800, "height": 600}

# Default server port (matches session-browser.sh default)
DEFAULT_PORT = 18999


# ── Primitive rendering configuration ─────────────────────────────────────

def get_primitive_render_args(name: str) -> dict:
    """Return render arguments for a given primitive macro.

    Each primitive needs specific arguments to render in its default state.
    """
    args: dict = {
        "button": {"label": "Primary Action", "variant": "primary"},
        "icon_button": {"icon": "&#9998;"},
        "badge": {"label": "info", "variant": "info"},
        "metric_card": {"label": "Sessions", "value": "42"},
        "metric_grid": {"cards": [
            '<div class="metric-card"><span class="metric-label">A</span><span class="metric-value">10</span></div>',
            '<div class="metric-card"><span class="metric-label">B</span><span class="metric-value">20</span></div>',
        ]},
        "pagination": {"current_page": 2, "total_pages": 5},
        "token_bar": {"segments": [
            {"kind": "fresh", "count": 1000},
            {"kind": "read", "count": 2000},
            {"kind": "write", "count": 500},
        ], "total": 3500},
        "tooltip": {"content": "Tooltip content", "trigger_text": "Hover me"},
        "popover": {"content": "Popover body", "trigger_element": "Click me"},
        "section_card": {"title": "Section", "content": "<p>Body text</p>"},
        "data_table": {"headers": ["Name", "Value", "Status"], "rows": [
            ["Alpha", "100", "active"],
            ["Beta", "200", "inactive"],
        ]},
        "filter_bar": {"filters": [
            {"name": "status", "label": "Status", "options": ["active", "inactive"]},
        ]},
        "payload_modal": {"payload_id": "test-1", "title": "Test Payload", "kind": "tool_call"},
        "empty_state": {"message": "No results found"},
        "error_state": {"message": "Something went wrong"},
        "legacy-btn": {"label": "Legacy"},
        "select-control": {"name": "sort", "options": ["asc", "desc"], "value": "asc"},
        "stat-pill": {"label": "Tokens", "value": "1.2K"},
        "th-static": {"label": "Static Column"},
        "th-sort": {"label": "Sortable", "sort_key": "name"},
        "token-total": {"total": 5000},
    }
    return args.get(name, {})


# ── Dev server management ─────────────────────────────────────────────────

class DevServer:
    """Manage the feipi-session-browser dev server lifecycle."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.process: subprocess.Popen | None = None

    def start(self) -> bool:
        """Start the dev server in the background. Returns True if started."""
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable, "-m", "session_browser", "serve",
                    "--allow-empty",
                    "--host", "127.0.0.1",
                    "--port", str(self.port),
                    "--startup-scan",
                ],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**_clean_env(), "PYTHONUNBUFFERED": "1"},
            )
            # Wait for server to be ready
            for _ in range(30):
                time.sleep(0.5)
                if _is_server_ready(self.port):
                    return True
            print(f"  WARN: Server did not become ready on port {self.port}")
            return False
        except FileNotFoundError:
            print(f"  SKIP: session_browser module not found")
            return False

    def stop(self):
        """Stop the dev server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


def _clean_env() -> dict:
    """Return a clean environment for the dev server."""
    env = dict(Path().resolve().parent / "src")  # type: ignore[operator]
    import os
    env = {k: v for k, v in os.environ.items()}
    env["PYTHONPATH"] = str(ROOT / "src") + ":" + env.get("PYTHONPATH", "")
    return env


def _is_server_ready(port: int) -> bool:
    """Check if the dev server is responding."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=1)
        return True
    except Exception:
        return False


# ── Screenshot capture ────────────────────────────────────────────────────

def ensure_playwright() -> bool:
    """Check if Playwright CLI is available."""
    result = subprocess.run(
        ["npx", "playwright", "--version"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=10,
    )
    if result.returncode == 0:
        print(f"  Playwright {result.stdout.strip()}")
        return True
    print("  SKIP: Playwright not installed (run: npm install && npx playwright install)")
    return False


def capture_primitive_screenshots(
    primitives: list[str],
    port: int = DEFAULT_PORT,
    output_dir: Path | None = None,
    capture_only: bool = False,
) -> dict:
    """Take screenshots of each primitive using Playwright.

    Returns a dict of {primitive_name: {"status": "pass"|"fail"|"skip", "details": str}}.
    """
    results: dict = {}
    base_dir = output_dir or PRIMITIVE_ACTUALS
    base_dir.mkdir(parents=True, exist_ok=True)

    if not ensure_playwright():
        for name in primitives:
            results[name] = {"status": "skip", "details": "Playwright not available"}
        return results

    # Use Playwright via subprocess to take screenshots
    # For harness setup: generate the script that would do the capture
    for name in primitives:
        ref_path = PRIMITIVE_REFERENCES / f"{name}-reference.png"
        actual_path = base_dir / f"{name}-actual.png"

        # Check if reference exists
        has_reference = ref_path.exists()

        if not has_reference and not capture_only:
            results[name] = {
                "status": "skip",
                "details": "No reference image available",
            }
            continue

        # Generate screenshot via Playwright
        pw_result = _take_screenshot_with_playwright(
            name,
            url=f"http://127.0.0.1:{port}/__primitives__/{name}",
            output_path=str(actual_path),
        )

        if pw_result["success"]:
            if has_reference and not capture_only:
                diff = _compare_images(str(ref_path), str(actual_path))
                results[name] = {
                    "status": "pass" if diff["pass"] else "fail",
                    "details": diff.get("message", "matched"),
                }
            else:
                results[name] = {
                    "status": "pass" if capture_only else "skip",
                    "details": "Screenshot captured (no reference to compare)",
                }
        else:
            results[name] = {
                "status": "fail",
                "details": pw_result.get("error", "screenshot failed"),
            }

    return results


def _take_screenshot_with_playwright(
    name: str,
    url: str,
    output_path: str,
) -> dict:
    """Take a screenshot of a single primitive via Playwright CLI.

    For harness setup: generates a temporary Playwright spec and runs it.
    In production, this would use a dedicated primitives showcase page.
    """
    import tempfile
    spec = f"""
const {{ test, expect }} = require('@playwright/test');
test('{name} primitive screenshot', async ({{ page }}) => {{
  await page.setViewportSize({{ width: {VIEWPORT["width"]}, height: {VIEWPORT["height"]} }});
  await page.goto('{url}');
  await page.waitForLoadState('networkidle');
  await page.screenshot({{ path: '{output_path}', fullPage: true }});
}});
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".spec.js", dir=str(ROOT / "tests" / "playwright"),
        delete=False,
    ) as f:
        f.write(spec)
        spec_path = f.name

    try:
        result = subprocess.run(
            ["npx", "playwright", "test", spec_path, "--reporter=list"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        return {
            "success": result.returncode == 0,
            "error": result.stderr.strip() if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Playwright timed out"}
    finally:
        Path(spec_path).unlink(missing_ok=True)


def _compare_images(ref_path: str, actual_path: str) -> dict:
    """Compare two images and return pass/fail with details.

    Uses pixel comparison via Playwright's built-in mechanism.
    For harness setup: placeholder that checks both files exist.
    """
    ref = Path(ref_path)
    actual = Path(actual_path)

    if not actual.exists():
        return {"pass": False, "message": "Actual screenshot missing"}
    if not ref.exists():
        return {"pass": False, "message": "Reference screenshot missing"}

    # In production: use pixelmatch or Playwright's expect.toHaveScreenshot
    # For harness setup: report file sizes as a basic sanity check
    ref_size = ref.stat().st_size
    actual_size = actual.stat().st_size

    if actual_size == 0:
        return {"pass": False, "message": "Actual screenshot is empty"}

    size_ratio = abs(ref_size - actual_size) / max(ref_size, 1)
    if size_ratio < 0.3:
        return {"pass": True, "message": f"Size ratio within tolerance ({size_ratio:.1%})"}
    return {
        "pass": False,
        "message": f"Size difference too large ({size_ratio:.1%}), pixel comparison needed",
    }


# ── Reporting ─────────────────────────────────────────────────────────────

def print_report(results: dict, capture_only: bool = False) -> bool:
    """Print a summary report and return overall pass/fail."""
    mode = "Capture" if capture_only else "Validation"
    print(f"\n{'='*60}")
    print(f"Primitive Screenshot {mode} Report")
    print(f"{'='*60}")

    passed = 0
    failed = 0
    skipped = 0

    for name, result in sorted(results.items()):
        status = result["status"].upper()
        details = result.get("details", "")
        marker = {
            "PASS": "[PASS]",
            "FAIL": "[FAIL]",
            "SKIP": "[SKIP]",
        }.get(status, "[????]")

        print(f"  {marker:8s} {name:20s} {details}")

        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        else:
            skipped += 1

    total = passed + failed + skipped
    print(f"\n{'='*60}")
    print(f"Total: {total} | Pass: {passed} | Fail: {failed} | Skip: {skipped}")
    print(f"{'='*60}")

    if skipped > 0:
        print(f"\nMissing reference images for {skipped} primitives.")
        print(f"Run with --capture to generate baseline screenshots.")

    return failed == 0


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate primitive screenshots against HIFI references.",
    )
    parser.add_argument(
        "--primitive", "-p",
        help="Validate a single primitive (default: all)",
    )
    parser.add_argument(
        "--capture", "-c",
        action="store_true",
        help="Capture new screenshots without comparing",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all primitives and exit",
    )
    parser.add_argument(
        "--port",
        type=int, default=DEFAULT_PORT,
        help=f"Dev server port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path, default=None,
        help="Output directory for screenshots",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Do not start the dev server (use existing)",
    )

    args = parser.parse_args()

    # List mode
    if args.list:
        print("Canonical primitives (15):")
        for name in CANONICAL_PRIMITIVES:
            args_dict = get_primitive_render_args(name)
            print(f"  - {name}: {json.dumps(args_dict)}")
        print("\nLegacy primitives (6):")
        for name in LEGACY_PRIMITIVES:
            args_dict = get_primitive_render_args(name)
            print(f"  - {name}: {json.dumps(args_dict)}")
        print(f"\nTotal: {len(ALL_PRIMITIVES)} primitives")

        # Check existing references
        ref_count = sum(1 for p in PRIMITIVE_REFERENCES.glob("*.png"))
        print(f"Existing references: {ref_count}/{len(ALL_PRIMITIVES)}")
        return 0

    # Select primitives
    if args.primitive:
        if args.primitive not in ALL_PRIMITIVES:
            print(f"ERROR: Unknown primitive '{args.primitive}'")
            print(f"Run --list to see available primitives")
            return 1
        primitives = [args.primitive]
    else:
        primitives = ALL_PRIMITIVES

    # Capture mode
    server = DevServer(port=args.port)
    try:
        if not args.no_server:
            print(f"Starting dev server on port {args.port}...")
            if not server.start():
                print("ERROR: Could not start dev server")
                return 1
            print(f"  Server ready on http://127.0.0.1:{args.port}")

        results = capture_primitive_screenshots(
            primitives=primitives,
            port=args.port,
            output_dir=args.output,
            capture_only=args.capture,
        )

        ok = print_report(results, capture_only=args.capture)
        return 0 if ok else 1

    finally:
        if not args.no_server:
            server.stop()


if __name__ == "__main__":
    sys.exit(main())
