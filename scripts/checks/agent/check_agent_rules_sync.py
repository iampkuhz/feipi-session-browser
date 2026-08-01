"""检查跨平台 Agent 规则是否与共享 policy manifest 保持一致。

同步检查可防止客户端入口遗漏保护范围或把 skipped 误写为通过。公开入口是
`check(arguments)`；返回诊断表示必需短语、受保护路径或安全语义缺失。
"""

from __future__ import annotations

from scripts.checks._framework import CheckResult, argument_parser, repository_root

ROOT = repository_root()

POLICY_MANIFEST = ROOT / "harness" / "agent-policy.manifest.yaml"


def _parse_yaml_list(text: str, key: str) -> list[str]:
    """从 YAML 文本中提取指定顶层字段下的字符串列表。"""
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


def _read_policy_protected_roots() -> list[str]:
    """返回共享 policy manifest 中声明的受保护路径。"""
    if not POLICY_MANIFEST.is_file():
        return []
    return _parse_yaml_list(POLICY_MANIFEST.read_text(encoding="utf-8"), "protected_roots")


def _read_required_phrases() -> list[str]:
    """读取 policy manifest 的必需短语；文件缺失时返回空列表。"""
    if not POLICY_MANIFEST.is_file():
        return []
    text = POLICY_MANIFEST.read_text(encoding="utf-8")
    return _parse_yaml_list(text, "required_phrases")


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回跨平台规约同步检查结果。"""
    parser = argument_parser(description='检查跨平台 Agent 规则同步')
    parser.parse_args(arguments)
    errors: list[str] = []

    if not POLICY_MANIFEST.is_file():
        return CheckResult.from_errors(
            [f"policy manifest 不存在: {POLICY_MANIFEST.relative_to(ROOT)}"]
        )

    agents_path = ROOT / "AGENTS.md"
    claude_path = ROOT / "CLAUDE.md"
    codex_path = ROOT / ".codex" / "model-instructions.md"

    agents_text = agents_path.read_text(encoding="utf-8") if agents_path.is_file() else ""
    claude_text = claude_path.read_text(encoding="utf-8") if claude_path.is_file() else ""
    codex_text = codex_path.read_text(encoding="utf-8") if codex_path.is_file() else ""

    # 先验证共享 manifest 明确声明的文本契约。
    required_phrases = _read_required_phrases()
    for phrase in required_phrases:
        if phrase not in agents_text:
            errors.append(f"AGENTS.md 缺少 required phrase: {phrase!r}")

    # 再验证受保护路径覆盖，避免入口短规则遗漏高风险目录。
    policy_roots = _read_policy_protected_roots()
    for root in policy_roots:
        if root not in agents_text:
            errors.append(f"AGENTS.md 缺少 policy manifest protected_root: {root}")

    # 最后检查跨平台共同的 skipped-not-pass 安全语义。
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

    return CheckResult.from_errors(errors)
