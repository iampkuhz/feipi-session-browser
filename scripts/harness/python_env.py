#!/usr/bin/env python3
"""Shared Python interpreter and dependency contract checks."""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_VERSION = (3, 10)
_RUNTIME_LOCK = "requirements.lock"
_DEV_LOCK = "requirements-dev.lock"
_TEST_PACKAGES = {"pytest", "pytest-xdist"}
_NORMALIZE_RE = re.compile(r"[-_.]+")
_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\s*(?:\[.*?\])?\s*(?:[<>=!~]=|===|@|;|$))")


def normalize_name(name: str) -> str:
    return _NORMALIZE_RE.sub("-", name).lower()


def _is_executable(path: str) -> bool:
    if os.sep in path or (os.altsep and os.altsep in path):
        return Path(path).expanduser().is_file() and os.access(Path(path).expanduser(), os.X_OK)
    return shutil.which(path) is not None


def _supports_python_version(executable: str) -> bool:
    if not _is_executable(executable):
        return False
    code = "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    try:
        result = subprocess.run(
            [executable, "-c", code],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        return False
    return result.returncode == 0


def python_candidates(repo_root: Path = REPO_ROOT) -> list[str]:
    candidates: list[str] = []
    explicit = os.environ.get("SESSION_BROWSER_PYTHON")
    if explicit:
        candidates.append(explicit)

    venv_dir = os.environ.get("SESSION_BROWSER_VENV_DIR")
    if venv_dir:
        candidates.append(str(Path(venv_dir).expanduser() / "bin" / "python"))
    else:
        candidates.append(str(repo_root / ".venv" / "bin" / "python"))

    candidates.extend(["python", "python3"])

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def resolve_python(repo_root: Path = REPO_ROOT) -> str:
    explicit = os.environ.get("SESSION_BROWSER_PYTHON")
    for candidate in python_candidates(repo_root):
        if _supports_python_version(candidate):
            return candidate
        if explicit and candidate == explicit:
            raise SystemExit(f"SESSION_BROWSER_PYTHON 不可执行或低于 Python 3.10：{explicit}")
    raise SystemExit("未找到可用 Python 解释器（需要 Python >= 3.10）。")


def _strip_comment(line: str) -> str:
    in_quote = False
    quote = ""
    for idx, char in enumerate(line):
        if char in {"'", '"'}:
            if in_quote and char == quote:
                in_quote = False
            elif not in_quote:
                in_quote = True
                quote = char
        elif char == "#" and not in_quote:
            return line[:idx]
    return line


def requirement_names(path: Path, *, _seen: set[Path] | None = None) -> list[str]:
    if _seen is None:
        _seen = set()
    path = path.resolve()
    if path in _seen:
        return []
    _seen.add(path)

    names: list[str] = []
    if not path.is_file():
        return names
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line.startswith("-r ") or line.startswith("--requirement "):
            include = line.split(maxsplit=1)[1]
            names.extend(requirement_names(path.parent / include, _seen=_seen))
            continue
        if line.startswith("-"):
            continue
        match = _REQ_NAME_RE.match(line)
        if match:
            names.append(normalize_name(match.group(1)))
    return names


def _parse_pyproject_arrays(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    deps: list[str] = []
    dev: list[str] = []
    current: str | None = None
    in_array = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "dependencies = [":
            current = "dependencies"
            in_array = True
            continue
        if line == "dev = [":
            current = "dev"
            in_array = True
            continue
        if in_array and line == "]":
            current = None
            in_array = False
            continue
        if in_array and current in {"dependencies", "dev"}:
            item = line.rstrip(",").strip().strip('"').strip("'")
            if item:
                (deps if current == "dependencies" else dev).append(normalize_name(item))
    return deps, dev


def pyproject_names(path: Path) -> tuple[list[str], list[str]]:
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        return _parse_pyproject_arrays(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    deps = [normalize_name(item) for item in project.get("dependencies", [])]
    dev = [normalize_name(item) for item in project.get("optional-dependencies", {}).get("dev", [])]
    return deps, dev


@dataclass(frozen=True)
class LockEntry:
    name: str
    version: str
    raw: str


def lock_entries(path: Path) -> list[LockEntry]:
    entries: list[LockEntry] = []
    if not path.is_file():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw).strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            entries.append(LockEntry(normalize_name(line), "", raw))
            continue
        name, version = line.split("==", 1)
        entries.append(LockEntry(normalize_name(name.strip()), version.strip(), raw))
    return entries


def _compare_sets(label: str, expected: list[str], actual: list[str]) -> list[str]:
    problems: list[str] = []
    expected_set = set(expected)
    actual_set = set(actual)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing:
        problems.append(f"{label} 缺少：{', '.join(missing)}")
    if extra:
        problems.append(f"{label} 多出：{', '.join(extra)}")
    return problems


def check_locks(repo_root: Path = REPO_ROOT) -> list[str]:
    problems: list[str] = []
    req_runtime = requirement_names(repo_root / "requirements.txt")
    req_dev = requirement_names(repo_root / "requirements-dev.txt")
    py_runtime, py_dev = pyproject_names(repo_root / "pyproject.toml")

    problems.extend(_compare_sets("pyproject dependencies 与 requirements.txt", req_runtime, py_runtime))
    problems.extend(_compare_sets("pyproject dev 与 requirements-dev.txt", req_dev, py_runtime + py_dev))

    lock_paths = [repo_root / _RUNTIME_LOCK, repo_root / _DEV_LOCK]
    for path in lock_paths:
        if not path.is_file():
            problems.append(f"缺少锁文件：{path.name}")

    runtime_entries = lock_entries(repo_root / _RUNTIME_LOCK)
    dev_entries = lock_entries(repo_root / _DEV_LOCK)
    problems.extend(_compare_sets(f"{_RUNTIME_LOCK}", req_runtime, [e.name for e in runtime_entries]))
    problems.extend(_compare_sets(f"{_DEV_LOCK}", req_dev, [e.name for e in dev_entries]))

    for lock_name, entries in ((_RUNTIME_LOCK, runtime_entries), (_DEV_LOCK, dev_entries)):
        seen: set[str] = set()
        for entry in entries:
            if entry.name in seen:
                problems.append(f"{lock_name} 重复依赖：{entry.name}")
            seen.add(entry.name)
            if not entry.version:
                problems.append(f"{lock_name} 未固定版本：{entry.raw}")
    return problems


def installed_problems(profile: str, repo_root: Path = REPO_ROOT) -> list[str]:
    if profile == "runtime":
        names = set(requirement_names(repo_root / "requirements.txt"))
    elif profile == "test":
        names = set(requirement_names(repo_root / "requirements.txt")) | _TEST_PACKAGES
    elif profile == "dev":
        names = set(requirement_names(repo_root / "requirements-dev.txt"))
    else:
        raise ValueError(f"unknown profile: {profile}")

    problems: list[str] = []
    for name in sorted(names):
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"缺少 Python 依赖：{name}")
    return problems


def print_report(repo_root: Path = REPO_ROOT) -> int:
    python = resolve_python(repo_root)
    print(f"[INFO] python: {python}")
    print(f"[INFO] python candidates: {', '.join(python_candidates(repo_root))}")
    print(f"[INFO] requirements: requirements.txt, requirements-dev.txt")
    print(f"[INFO] locks: {_RUNTIME_LOCK}, {_DEV_LOCK}")
    problems = check_locks(repo_root)
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return 1
    print("[PASS] dependency declarations match lock files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("resolve")
    sub.add_parser("report")
    sub.add_parser("check-locks")
    installed = sub.add_parser("check-installed")
    installed.add_argument("--profile", choices=["runtime", "test", "dev"], default="runtime")
    args = parser.parse_args(argv)

    if args.cmd == "resolve":
        print(resolve_python())
        return 0
    if args.cmd == "report":
        return print_report()
    if args.cmd == "check-locks":
        problems = check_locks()
    else:
        problems = installed_problems(args.profile)
    if problems:
        for problem in problems:
            print(f"[FAIL] {problem}", file=sys.stderr)
        return 1
    print("[PASS] " + ("dependency locks consistent" if args.cmd == "check-locks" else f"{args.profile} dependencies installed"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
