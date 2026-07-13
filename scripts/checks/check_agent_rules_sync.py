#!/usr/bin/env python3
"""检查跨平台 agent 规则同步一致性。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

from scripts.checks._framework import repository_root

ROOT = repository_root()

from scripts.agent_runtime import policy as runtime_policy  # noqa: E402

POLICY_MANIFEST = ROOT / "harness" / "agent-policy.manifest.yaml"
RUNTIME_MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
GATE_NAME = "agentRulesSync"


# 输出失败信息并返回非零退出码。
def fail(msg: str) -> int:
    """参数：
        msg: 失败原因。

    返回：
        固定返回 1。
    """
    print(f"[{GATE_NAME}] FAIL: {msg}")
    return 1


# 从 YAML 文本中解析指定顶层 key 下的列表值。
def _parse_yaml_list(text: str, key: str) -> list[str]:
    """参数：
        text: manifest 原始文本。
        key: 需要解析的顶层字段名。

    返回：
        该字段下的字符串列表。
    """
    result: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(key + ":"):
            in_section = True
            continue
        if in_section:
            if not stripped or (not line.startswith(" ") and ":" in stripped):
                break
            if stripped.startswith("- "):
                val = stripped[2:].strip().strip('"').strip("'")
                result.append(val)
    return result


# 从 runtime manifest 中读取受保护路径列表。
def _read_runtime_protected_roots() -> list[str]:
    """返回：
    runtime manifest 中声明的受保护路径。
    """
    if not RUNTIME_MANIFEST.is_file():
        return []
    return runtime_policy.protected_roots(ROOT)


# 从 policy manifest 中读取必需短语列表。
def _read_required_phrases() -> list[str]:
    """返回：
    policy manifest 中声明的必需短语。
    """
    if not POLICY_MANIFEST.is_file():
        return []
    text = POLICY_MANIFEST.read_text(encoding="utf-8")
    return _parse_yaml_list(text, "required_phrases")


# 执行跨平台规则同步检查并返回退出码。


def main() -> int:
    """返回：
    通过返回 0，失败返回非零。
    """

    errors: list[str] = []

    if not POLICY_MANIFEST.is_file():
        return fail(f"policy manifest 不存在: {POLICY_MANIFEST.relative_to(ROOT)}")

    agents_path = ROOT / "AGENTS.md"
    claude_path = ROOT / "CLAUDE.md"
    codex_path = ROOT / ".codex" / "model-instructions.md"

    agents_text = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""
    claude_text = claude_path.read_text(encoding="utf-8") if claude_path.is_file() else ""
    codex_text = codex_path.read_text(encoding="utf-8") if codex_path.is_file() else ""

    # AGENTS.md 必须包含 policy manifest 声明的全部必需短语。
    required_phrases = _read_required_phrases()
    for phrase in required_phrases:
        if phrase not in agents_text:
            errors.append(f"AGENTS.md 缺少 required phrase: {phrase!r}")

    # AGENTS.md 受保护路径必须覆盖 runtime manifest 声明的全部根路径。
    runtime_roots = _read_runtime_protected_roots()
    if runtime_roots:
        for root in runtime_roots:
            if root not in agents_text:
                errors.append(f"AGENTS.md 缺少 runtime manifest protected_root: {root}")

    # 三份规约文件都必须包含跳过不得视为通过的语义。
    skip_keywords = {"skipped", "跳过"}
    negation_keywords = {"不得", "不能", "不算", "不应"}
    pass_keywords = {"PASS", "pass"}

    policy_files = {"AGENTS.md": agents_text, "CLAUDE.md": claude_text}
    if codex_text:
        policy_files[".codex/model-instructions.md"] = codex_text

    for fname, ftext in policy_files.items():
        has_skip = any(kw in ftext for kw in skip_keywords)
        has_negation = any(kw in ftext for kw in negation_keywords)
        has_pass = any(kw in ftext for kw in pass_keywords)
        if not (has_skip and has_negation and has_pass):
            missing: list[str] = []
            if not has_skip:
                missing.append("skipped/跳过")
            if not has_negation:
                missing.append("不得/不能")
            if not has_pass:
                missing.append("PASS/pass")
            errors.append(f"{fname} 缺少 skipped-not-pass 语义关键词: {', '.join(missing)}")

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0
