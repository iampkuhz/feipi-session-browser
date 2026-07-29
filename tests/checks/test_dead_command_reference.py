from __future__ import annotations

from pathlib import Path

from scripts.checks.repository import check_dead_command_reference as checker

ROOT = Path(__file__).resolve().parents[2]


def _write(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# synthetic executable\n", encoding="utf-8")


def test_reference_status_covers_missing_non_public_public_and_diagnostic(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "scripts/public.py")
    _write(tmp_path, "scripts/private.py")
    _write(tmp_path, "scripts/checks/repository/check_named.py")
    _write(tmp_path, "scripts/checks/catalog_leaf.py")

    public = frozenset({"scripts/public.py", "scripts/missing.py"})
    patterns = ("scripts/checks/*/check_*.py",)
    catalog = frozenset({"scripts/checks/catalog_leaf.py"})

    assert (
        checker.reference_status(tmp_path, "scripts/missing.py", public, patterns, catalog)
        == "missing"
    )
    assert (
        checker.reference_status(tmp_path, "scripts/private.py", public, patterns, catalog)
        == "non-public"
    )
    assert (
        checker.reference_status(tmp_path, "scripts/public.py", public, patterns, catalog)
        == "public"
    )
    assert (
        checker.reference_status(
            tmp_path, "scripts/checks/repository/check_named.py", public, patterns, catalog
        )
        == "diagnostic"
    )
    assert (
        checker.reference_status(
            tmp_path, "scripts/checks/catalog_leaf.py", public, patterns, catalog
        )
        == "diagnostic"
    )


def test_scan_references_extracts_only_explicit_script_commands(tmp_path: Path) -> None:
    source = tmp_path / "commands.md"
    source.write_text(
        "\n".join(
            (
                "`python3 scripts/gates/cli.py --tier required`",
                "`bash scripts/harness/doctor.sh`",
                "`./scripts/session-browser.sh test`",
                "reference scripts/gates/catalog.py without executing it",
            )
        ),
        encoding="utf-8",
    )

    references = checker.scan_references(tmp_path, (source,))

    assert [(item.line, item.target) for item in references] == [
        (1, "scripts/gates/cli.py"),
        (2, "scripts/harness/doctor.sh"),
        (3, "scripts/session-browser.sh"),
    ]


def test_repository_has_no_dead_or_private_command_references() -> None:
    assert checker.check_repository(ROOT) == ()
