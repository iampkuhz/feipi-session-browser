import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "quality" / "check_java_api_snapshot.py"

spec = importlib.util.spec_from_file_location("check_java_api_snapshot", SCRIPT)
api_snapshot = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = api_snapshot
spec.loader.exec_module(api_snapshot)


def write_java(root: Path, module: str, name: str, source: str) -> Path:
    path = root / module / "src" / "main" / "java" / "example" / f"{name}.java"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_snapshot_output_is_deterministically_sorted(tmp_path):
    source_b = """
        package example;
        public interface Beta {
          String name();
        }
    """
    source_a = """
        package example;
        public record Alpha(String id, int count) {
          public String label() { return id; }
        }
    """
    write_java(tmp_path, "module-b", "Beta", source_b)
    write_java(tmp_path, "module-a", "Alpha", source_a)

    first = api_snapshot.generate_snapshot(tmp_path)

    reversed_root = tmp_path / "reversed"
    write_java(reversed_root, "module-a", "Alpha", source_a)
    write_java(reversed_root, "module-b", "Beta", source_b)

    second = api_snapshot.generate_snapshot(reversed_root)

    assert first == second
    body = [line for line in first.splitlines() if line and not line.startswith("#")]
    assert body == sorted(body)
    assert "component example.Alpha count: int" in body
    assert "method example.Beta public String name()" in body


def test_check_reports_unified_diff_for_public_api_drift(tmp_path):
    write_java(
        tmp_path,
        "module-a",
        "Api",
        """
        package example;
        public class Api {
          public String existing() { return "ok"; }
        }
        """,
    )
    snapshot = tmp_path / "java-public-api.txt"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--write", "--java-root", str(tmp_path), "--snapshot", str(snapshot)],
        check=True,
        text=True,
        capture_output=True,
    )

    write_java(
        tmp_path,
        "module-a",
        "Api",
        """
        package example;
        public class Api {
          public String added() { return "new"; }
          public String existing() { return "ok"; }
        }
        """,
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--java-root", str(tmp_path), "--snapshot", str(snapshot)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "--- " in result.stderr
    assert "+++ current-java-public-api" in result.stderr
    assert "+method example.Api public String added()" in result.stderr
