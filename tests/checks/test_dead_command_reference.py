from __future__ import annotations

from pathlib import Path

from scripts.gates.checks.repository import check_file_boundary as checker

ROOT = Path(__file__).resolve().parents[2]


def _write(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# synthetic executable\n", encoding="utf-8")


def test_reference_status_covers_missing_non_public_and_public(tmp_path: Path) -> None:
    _write(tmp_path, "scripts/public.py")
    _write(tmp_path, "scripts/private.py")

    public = frozenset({"scripts/public.py", "scripts/missing.py"})

    assert checker._reference_status(tmp_path, "scripts/missing.py", public) == "missing"
    assert checker._reference_status(tmp_path, "scripts/private.py", public) == "non-public"
    assert checker._reference_status(tmp_path, "scripts/public.py", public) == "public"


def test_scan_references_extracts_only_explicit_script_commands(tmp_path: Path) -> None:
    source = tmp_path / "commands.md"
    source.write_text(
        "\n".join(
            (
                "`python3 scripts/gates/cli.py run --mode incremental`",
                "`bash scripts/harness/doctor.sh`",
                "`./scripts/session-browser.sh test`",
                "reference scripts/gates/catalog/registry.py without executing it",
            )
        ),
        encoding="utf-8",
    )

    references = checker._scan_references(tmp_path, (source,))

    assert [(item.line, item.target) for item in references] == [
        (1, "scripts/gates/cli.py"),
        (2, "scripts/harness/doctor.sh"),
        (3, "scripts/session-browser.sh"),
    ]


def test_manifest_does_not_advertise_internal_check_files_as_executables() -> None:
    assert 'diagnostic_executables' not in checker._manifest(ROOT)
