#!/usr/bin/env python3
"""检查 agent 规约体积是否在限制内。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
POLICY_MANIFEST = ROOT / "harness" / "agent-policy.manifest.yaml"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"
GATE_NAME = "agentPolicySize"

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered

TRIGGER_PATTERNS = [
    'AGENTS.md',
    'CLAUDE.md',
    '.codex/config.toml',
    'harness/agent-policy.manifest.yaml',
    'scripts/quality/check_agent_policy_size.py',
]


# 输出失败信息并返回非零退出码。
def fail(msg: str) -> int:
    """参数：
        msg: 失败原因。

    返回：
        固定返回 1。
    """
    print(f"[{GATE_NAME}] FAIL: {msg}")
    return 1


# 从 policy manifest 文本中解析 size_limits 映射。
def _parse_size_limits(text: str) -> dict[str, int]:
    """参数：
        text: manifest 原始文本。

    返回：
        文件名到字节上限的映射。
    """
    result: dict[str, int] = {}
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "size_limits:":
            in_section = True
            continue
        if in_section:
            if not stripped or (not line.startswith(" ") and ":" in stripped):
                break
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                try:
                    result[key] = int(val)
                except ValueError:
                    pass
    return result


# 从 Codex 项目配置中读取单文件体积上限。
def _read_codex_max() -> int | None:
    """返回：
        project_doc_max_bytes 整数值；配置不存在时返回 None。
    """
    if not CODEX_CONFIG.is_file():
        return None
    for line in CODEX_CONFIG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"project_doc_max_bytes\s*=\s*(\d+)", line.strip())
        if m:
            return int(m.group(1))
    return None


# 执行规约体积检查并返回退出码。
def main() -> int:
    """返回：
        通过返回 0，失败返回非零。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
        skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)
    else:
        skip_if_not_triggered(None, TRIGGER_PATTERNS)

    if not POLICY_MANIFEST.is_file():
        return fail(f"policy manifest 不存在: {POLICY_MANIFEST.relative_to(ROOT)}")

    manifest_text = POLICY_MANIFEST.read_text(encoding="utf-8")
    size_limits = _parse_size_limits(manifest_text)
    if not size_limits:
        return fail("policy manifest 缺少 size_limits")

    agents_limit = size_limits.get("AGENTS.md")
    claude_limit = size_limits.get("CLAUDE.md")
    if agents_limit is None:
        return fail("policy manifest size_limits 缺少 AGENTS.md 限制")

    agents_file = ROOT / "AGENTS.md"
    claude_file = ROOT / "CLAUDE.md"

    errors: list[str] = []

    # 检查 AGENTS.md 体积不超过 manifest 声明的上限。
    if agents_file.is_file():
        agents_size = agents_file.stat().st_size
        print(f"[{GATE_NAME}] AGENTS.md: {agents_size} bytes (limit: {agents_limit})")
        if agents_size > agents_limit:
            errors.append(
                f"AGENTS.md {agents_size} bytes 超过限制 {agents_limit} bytes"
            )
    else:
        return fail("AGENTS.md 不存在")

    # 检查 CLAUDE.md 体积不超过 soft limit；超过时仅告警。
    if claude_file.is_file() and claude_limit is not None:
        claude_size = claude_file.stat().st_size
        print(f"[{GATE_NAME}] CLAUDE.md: {claude_size} bytes (limit: {claude_limit})")
        if claude_size > claude_limit:
            print(
                f"[{GATE_NAME}] WARN: CLAUDE.md {claude_size} bytes "
                f"超过 soft limit {claude_limit} bytes"
            )

    # 检查 Codex 配置留有足够的余量。
    codex_max = _read_codex_max()
    if codex_max is not None and agents_file.is_file():
        agents_size = agents_file.stat().st_size
        needed = agents_size + 100
        print(
            f"[{GATE_NAME}] Codex project_doc_max_bytes: {codex_max} "
            f"(need >= {needed})"
        )
        if codex_max < needed:
            errors.append(
                f".codex/config.toml project_doc_max_bytes={codex_max} "
                f"< AGENTS.md size({agents_size}) + 100 = {needed}"
            )

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
