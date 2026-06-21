"""Evaluate Bash commands before Claude Code executes them.

The pre-bash hook calls this policy to block destructive commands and secret reads while
allowing normal shell usage. Block decisions return status ``BLOCK`` and should exit 2;
warning decisions return ``PASS`` with advisory text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# 01. 评估结果
@dataclass
class BashPolicyDecision:
    """Decision returned by the pre-bash command policy.

    Attributes:
        allowed: Whether the command may execute.
        status: Hook status such as ``PASS`` or ``BLOCK``.
        reason: Blocking reason shown to the user.
        warnings: Advisory messages for allowed but risky commands.
    """

    allowed: bool
    status: str
    reason: str = ''
    warnings: list[str] = field(default_factory=list)


# 02. 危险命令规则: 只 hard block 少数不可接受行为。
BLOCK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'(^|[;&|]\s*)sudo\s+rm\s+-[^\n]*r[^\n]*f', re.I), '禁止 sudo rm -rf。'),
    (
        re.compile(r"(^|[;&|]\s*)rm\s+-[^\n]*r[^\n]*f\s+(/|['\"]?/['\"]?)\s*($|[;&|])", re.I),
        '禁止 rm -rf /。',
    ),
    (
        re.compile(r'(^|[;&|]\s*)rm\s+-[^\n]*r[^\n]*f\s+(~|\$HOME)(/|\s|$)', re.I),
        '禁止 rm -rf ~ 或 $HOME。',
    ),
    (re.compile(r'\bgit\s+reset\s+--hard\b', re.I), '禁止 git reset --hard 破坏未提交改动。'),
    (
        re.compile(
            r'\bgit\s+clean\s+-[^\n]*f[^\n]*d[^\n]*x\b|\bgit\s+clean\s+-[^\n]*x[^\n]*d[^\n]*f\b',
            re.I,
        ),
        '禁止 git clean -fdx。',
    ),
    (re.compile(r'\bchmod\s+-R\s+777\s+/\b', re.I), '禁止 chmod -R 777 /。'),
    (re.compile(r'\bdd\s+if=.*\s+of=/dev/', re.I), '禁止 dd 写入 /dev 设备。'),
    (
        re.compile(r'\bcat\s+~/(?:\.claude|\.codex|\.qoder)/.*\.jsonl\b', re.I),
        '禁止直接 cat 大段真实 session jsonl。请用 head/sed/rg 局部读取。',
    ),
    (
        re.compile(
            r'\b(cat|grep|rg)\b.*(~/(?:\.ssh|\.aws)|id_rsa|id_ed25519|aws_access_key|secret_access_key)',
            re.I,
        ),
        '禁止读取或输出 SSH/AWS 密钥。',
    ),
]

WARN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r'\bcurl\b[^\n|;]*\|\s*(sh|bash)\b', re.I),
        'curl | sh 安装脚本存在供应链风险; 建议先下载并审计。',
    ),
    (
        re.compile(r'\bwget\b[^\n|;]*\|\s*(sh|bash)\b', re.I),
        'wget | sh 安装脚本存在供应链风险; 建议先下载并审计。',
    ),
]


# 03. 命令评估
def evaluate_command(command: str) -> BashPolicyDecision:
    """Evaluate a shell command for pre-bash hook enforcement.

    Args:
        command: Raw shell command from Claude Code hook input.

    Returns:
        ``BashPolicyDecision`` with ``allowed=False`` for hard blocks, or ``allowed=True``
        with optional warnings for commands that should be reviewed by the user.
    """
    cmd = command.strip()
    for pattern, reason in BLOCK_PATTERNS:
        if pattern.search(cmd):
            return BashPolicyDecision(allowed=False, status='BLOCK', reason=reason)

    warnings = [reason for pattern, reason in WARN_PATTERNS if pattern.search(cmd)]
    return BashPolicyDecision(allowed=True, status='PASS', warnings=warnings)


# 04. 自测试
def _self_test() -> None:
    """Run local assertions for command blocking and warning rules."""
    assert not evaluate_command('rm -rf /').allowed
    assert not evaluate_command('git reset --hard HEAD').allowed
    assert not evaluate_command('git clean -fdx').allowed
    assert evaluate_command('pytest -q').allowed
    assert evaluate_command('git diff').allowed
    assert evaluate_command('curl https://x/install.sh | sh').allowed
    assert evaluate_command('curl https://x/install.sh | sh').warnings


if __name__ == '__main__':
    _self_test()
    print('bash_policy self-test PASS')
