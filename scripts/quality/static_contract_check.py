from __future__ import annotations

from pathlib import Path
import re


# 01. 静态资源契约检查
def check_static(repo_root: Path) -> list[str]:
    failures: list[str] = []
    static = repo_root / "src/session_browser/web/static"
    if not static.exists():
        return [f"静态资源目录不存在：{static}"]

    for path in list(static.rglob("*.css")) + list(static.rglob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(repo_root).as_posix()

        if path.suffix == ".css":
            if re.search(r"!important", text):
                failures.append(f"{rel}: 避免新增 !important，除非有明确 contract 说明。")
            if re.search(r"position\s*:\s*fixed", text) and "modal" not in rel.lower():
                failures.append(f"{rel}: fixed 布局需确认是否符合桌面端 contract。")

        if path.suffix == ".js":
            if "eval(" in text:
                failures.append(f"{rel}: 禁止 eval。")
            if "innerHTML" in text and "sanitize" not in text.lower():
                failures.append(f"{rel}: innerHTML 需要 sanitize 或 contract 说明。")
    return failures


# 02. CLI
def main() -> int:
    failures = check_static(Path.cwd())
    if failures:
        for item in failures:
            print(item)
        return 1
    print("static contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
