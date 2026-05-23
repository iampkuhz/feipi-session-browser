from __future__ import annotations


# 01. target -> required gate 矩阵
QUALITY_TARGETS: dict[str, list[str]] = {
    "session-detail": [
        "pythonCompile",
        "templateContract",
        "staticCssContract",
        "browserLayout",
        "pytest",
    ],
    "python-src": [
        "pythonCompile",
        "pytest",
    ],
    "hook-runtime": [
        "settingsJson",
        "bashSyntax",
        "pythonCompile",
        "hookSelfTest",
        "pytest",
        "doctor",
        "repoStructure",
    ],
    "harness": [
        "bashSyntax",
        "pythonCompile",
        "doctor",
        "repoStructure",
        "harnessStructure",
        "openspecLayout",
    ],
}


# 02. 查询函数
def required_gates_for_target(target: str) -> list[str]:
    return list(QUALITY_TARGETS.get(target, []))


# 03. target 校验
def validate_target(target: str) -> None:
    if target not in QUALITY_TARGETS:
        raise ValueError(f"未知 quality target：{target}")
