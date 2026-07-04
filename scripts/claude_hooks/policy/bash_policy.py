"""提供 bash policy 脚本能力。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# 01. 评估结果
@dataclass
class BashPolicyDecision:
    """表示 BashPolicyDecision 的策略判定结果。

    属性：
        allowed: 是否允许继续执行。
        status: 状态值。
        reason: 阻断或放行原因。
        warnings: 警告列表。
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

READ_ONLY_PREFIXES = (
    'cat ',
    'grep ',
    'rg ',
    'sed -n ',
    'head ',
    'tail ',
    'ls',
    'find ',
    'pwd',
    'git status',
    'git diff',
    'git log',
    'git show',
    'git rev-parse',
    'git ls-files',
)

WRITE_SHELL_TOKENS = re.compile(r'(^|[^<])>>?|(?:^|[;&|]\s*)tee\b|\bapply_patch\b')


# 判断是否读取 仅 命令。
def is_read_only_command(command: str) -> bool:
    """参数：
        command: 待执行的命令。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    cmd = command.strip()
    if not cmd or WRITE_SHELL_TOKENS.search(cmd):
        return False
    parts = [part.strip() for part in re.split(r'\s*(?:&&|;)\s*', cmd) if part.strip()]
    if not parts:
        return False
    for part in parts:
        normalized = re.sub(r'\s+', ' ', part)
        if normalized in {'ls', 'pwd'}:
            continue
        if not any(normalized.startswith(prefix) for prefix in READ_ONLY_PREFIXES):
            return False
    return True


# 维护评估 命令。
def evaluate_command(command: str) -> BashPolicyDecision:
    """参数：
        command: 原始shell 命令从Claude Code hook 输入。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
    """
    cmd = command.strip()
    for pattern, reason in BLOCK_PATTERNS:
        if pattern.search(cmd):
            return BashPolicyDecision(allowed=False, status='BLOCK', reason=reason)

    warnings = [reason for pattern, reason in WARN_PATTERNS if pattern.search(cmd)]
    return BashPolicyDecision(allowed=True, status='PASS', warnings=warnings)


# 运行脚本自测试场景。
def _self_test() -> None:
    assert not evaluate_command('rm -rf /').allowed
    assert not evaluate_command('git reset --hard HEAD').allowed
    assert not evaluate_command('git clean -fdx').allowed
    assert evaluate_command('pytest -q').allowed
    assert evaluate_command('git diff').allowed
    assert evaluate_command('curl https://x/install.sh | sh').allowed
    assert evaluate_command('curl https://x/install.sh | sh').warnings
    assert is_read_only_command('git status --short && rg -n foo scripts')
    assert not is_read_only_command('python3 scripts/x.py')
    assert not is_read_only_command('sed -n 1p a > b')


if __name__ == '__main__':
    _self_test()
    print('bash_policy self-test PASS')
