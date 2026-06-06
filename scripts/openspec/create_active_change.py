#!/usr/bin/env python3
"""Create an active OpenSpec change and write tmp/active_change.json sentinel.

Usage:
    python3 scripts/openspec/create_active_change.py \\
        --change-id <kebab-case-id> \\
        --source "<source description>" \\
        [--title "<optional title, defaults to change-id>"]

This script is idempotent for change files: re-running with the same
--change-id does not overwrite existing change files.  The active sentinel is
always updated to the requested change because only one OpenSpec change can be
active for protected edits.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── Constants ────────────────────────────────────────────────────────────────

KEBAB_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

PROTECTED_ROOTS = [
    "openspec/",
    "harness/",
    ".claude/",
    ".codex/",
    ".qoder/",
    "CLAUDE.md",
    "AGENTS.md",
]

REQUIRED_GATES = [
    "scripts/openspec/validate_layout.py",
    "scripts/openspec/validate_schema.py",
    "scripts/openspec/validate_active_change.py",
    "scripts/harness/validate_harness_structure.py",
]

TEMPLATE_FILES = {
    "proposal.md": "proposal.md",
    "design.md": "design.md",
    "tasks.md": "tasks.md",
    "specs/spec.md": "spec.md",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def validate_change_id(change_id: str) -> str | None:
    """Return an error message if change_id is invalid, or None."""
    if not change_id:
        return "change-id is required and cannot be empty"
    if not KEBAB_RE.match(change_id):
        return (
            f"change-id '{change_id}' is not valid kebab-case. "
            "Use only lowercase letters, digits, and hyphens, starting with a letter or digit."
        )
    if " " in change_id or "/" in change_id:
        return f"change-id '{change_id}' must not contain spaces or slashes"
    return None


def _templates_dir(root: Path) -> Path:
    """Locate the templates directory."""
    candidates = [
        root / ".claude" / "skills" / "change" / "templates",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]  # return best guess even if missing


def write_file_if_missing(path: Path, content: str, label: str = "") -> bool:
    """Write *content* to *path* only if the file does not already exist.

    Returns True if the file was created, False if it already existed.
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def copy_template_if_missing(
    change_dir: Path,
    dest_rel: str,
    template_name: str,
    templates_dir: Path,
    change_id: str,
) -> bool:
    """Copy a template into the change directory if the destination is missing.

    Performs a simple placeholder substitution: ``<change-id>`` and
    ``<capability>`` in the template body are replaced with *change_id*.

    Returns True if the file was created.
    """
    dest = change_dir / dest_rel
    if dest.exists():
        return False

    tmpl_path = templates_dir / template_name
    if tmpl_path.exists():
        content = tmpl_path.read_text(encoding="utf-8")
    else:
        # Fallback: minimal content if template is absent
        content = f"# {dest_rel}\n"

    content = content.replace("<change-id>", change_id)
    content = content.replace("<capability>", change_id)

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return True


# ── Main logic ───────────────────────────────────────────────────────────────

def create_active_change(
    change_id: str,
    source: str,
    title: str | None = None,
    root: Path | None = None,
) -> dict:
    """Create the change directory structure and active_change.json sentinel.

    Returns a summary dict describing what was created / already existed.
    """
    if root is None:
        root = Path.cwd()

    title = title or change_id
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    change_dir = root / "openspec" / "changes" / change_id
    agent_dir = root / "tmp"
    active_change_file = agent_dir / "active_change.json"

    created: list[str] = []
    existed: list[str] = []
    updated: list[str] = []

    # --- Change directory and templates ---
    if not change_dir.exists():
        change_dir.mkdir(parents=True, exist_ok=True)
        created.append(f"openspec/changes/{change_id}/")
    else:
        existed.append(f"openspec/changes/{change_id}/")

    td = _templates_dir(root)

    for dest_rel, tmpl_name in TEMPLATE_FILES.items():
        ok = copy_template_if_missing(change_dir, dest_rel, tmpl_name, td, change_id)
        if ok:
            created.append(f"openspec/changes/{change_id}/{dest_rel}")
        else:
            existed.append(f"openspec/changes/{change_id}/{dest_rel}")

    # --- tmp/ directory ---
    if not agent_dir.exists():
        agent_dir.mkdir(parents=True, exist_ok=True)
        created.append("tmp/")
    else:
        existed.append("tmp/")

    # --- tmp/active_change.json ---
    sentinel = {
        "change_id": change_id,
        "change_path": f"openspec/changes/{change_id}/",
        "started_at": now,
        "source_request": source,
        "protected_roots": PROTECTED_ROOTS,
        "required_gates": REQUIRED_GATES,
    }

    if not active_change_file.exists():
        active_change_file.write_text(
            json.dumps(sentinel, indent=2) + "\n", encoding="utf-8"
        )
        created.append("tmp/active_change.json")
    else:
        existed.append("tmp/active_change.json")
        try:
            existing = json.loads(active_change_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

        if existing.get("change_id") == change_id:
            sentinel["started_at"] = existing.get("started_at") or now
            sentinel["source_request"] = existing.get("source_request") or source
        else:
            updated.append("tmp/active_change.json")

        active_change_file.write_text(
            json.dumps(sentinel, indent=2) + "\n", encoding="utf-8"
        )

    return {
        "change_id": change_id,
        "created": created,
        "existed": existed,
        "updated": updated,
        "sentinel_path": str(active_change_file),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an active OpenSpec change and sentinel file.",
    )
    parser.add_argument(
        "--change-id",
        required=True,
        help="Kebab-case change identifier (e.g. my-feature-name).",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source of the change request (e.g. 'harness hardening task pack').",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional human-readable title (defaults to change-id).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Validate change-id
    err = validate_change_id(args.change_id)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    result = create_active_change(
        change_id=args.change_id,
        source=args.source,
        title=args.title,
    )

    # Report
    if result["created"]:
        print(f"Created change '{result['change_id']}':")
        for p in result["created"]:
            print(f"  + {p}")
    if result["existed"]:
        print(f"Already existed (skipped):")
        for p in result["existed"]:
            print(f"    {p}")
    if result["updated"]:
        print("Updated active change:")
        for p in result["updated"]:
            print(f"  ~ {p}")
    if not result["created"] and not result["updated"]:
        print(f"Change '{result['change_id']}' already fully exists — no-op.")

    print(f"\nSentinel: {result['sentinel_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
