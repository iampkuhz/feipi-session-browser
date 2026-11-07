"""真实 Gradle task 的 SQLite native 裁剪回归。"""

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _source() -> str:
    build = (ROOT / "java/app-cli/build.gradle.kts").read_text()
    start = build.index("val sqliteNativePath =")
    end = build.index("\nval runtimeJars", start)
    return build[start:end]


def _fixture(
    tmp_path: Path,
    *,
    signed: bool = False,
    natives: tuple[str, ...] = (
        "Linux/x86_64/lib.so",
        "Linux-Musl/x86_64/lib.so",
        "Mac/aarch64/lib.dylib",
        "Windows/x86_64/sqlite.dll",
    ),
) -> Path:
    project = tmp_path / "fixture"
    project.mkdir()
    jar = project / "sqlite-jdbc-1.jar"
    with zipfile.ZipFile(jar, "w") as archive:
        for name in (
            "org/sqlite/JDBC.class",
            "META-INF/services/java.sql.Driver",
            "LICENSE",
            *[f"org/sqlite/native/{n}" for n in natives],
        ):
            archive.writestr(name, name.encode())
        if signed:
            archive.writestr("META-INF/TEST.SF", b"signature")
    gradle = f'''import org.gradle.api.tasks.bundling.Zip
import java.util.zip.ZipFile
plugins {{ java }}
dependencies {{ runtimeOnly(files("{jar.as_posix()}")) }}
{_source()}
'''
    (project / "build.gradle.kts").write_text(gradle)
    return project


def _run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "java/gradlew"), "-p", str(project), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )


def test_native_sqlite_packaging_task_behavior_and_reuse(tmp_path: Path) -> None:
    project = _fixture(tmp_path)
    first = _run(project, "nativeSqliteJar", "--configuration-cache")
    assert first.returncode == 0, first.stdout[-4000:]
    second = _run(project, "nativeSqliteJar", "--configuration-cache")
    assert second.returncode == 0, second.stdout[-4000:]
    assert "UP-TO-DATE" in second.stdout
    assert "Reusing configuration cache" in second.stdout
    output = project / "build/native-libs/sqlite-jdbc-1.jar"
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert {"org/sqlite/JDBC.class", "META-INF/services/java.sql.Driver", "LICENSE"} <= names
        native = {
            name
            for name in names
            if name.startswith("org/sqlite/native/") and not name.endswith("/")
        }
        assert native and all(name.startswith("org/sqlite/native/Mac/aarch64/") for name in native)
        for name in names:
            if name.endswith("/"):
                continue
            assert archive.read(name) == name.encode()


def test_native_sqlite_task_fails_closed_for_missing_or_signed_jar(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    missing = _fixture(
        missing_root,
        natives=("Windows/x86_64/sqlite.dll",),
    )
    result = _run(missing, "nativeSqliteJar", "--no-build-cache")
    assert result.returncode != 0 and "缺少目标 native" in result.stdout

    signed_root = tmp_path / "signed"
    signed_root.mkdir()
    signed = _fixture(signed_root, signed=True)
    result = _run(signed, "nativeSqliteJar", "--no-build-cache")
    assert result.returncode != 0 and "不能裁剪已签名" in result.stdout
