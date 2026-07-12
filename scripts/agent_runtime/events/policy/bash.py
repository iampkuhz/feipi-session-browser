"""判定跨平台 PreToolUse Bash 命令的安全策略与只读属性。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path


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
SHELL_EXPANSION_TOKENS = re.compile(r'\$\(|`')

PRIMARY_GIT_READ_ONLY = {
    'status',
    'diff',
    'log',
    'show',
    'rev-parse',
    'ls-files',
    'ls-tree',
    'cat-file',
    'merge-base',
    'describe',
    'name-rev',
    'for-each-ref',
}


def _inside(path: Path, root: Path) -> bool:
    """按 realpath 判断路径是否位于目标 checkout，覆盖符号链接入口。"""
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def _shell_tokens(command: str) -> list[str]:
    """保留控制符拆分 shell token；无法解析时返回空列表并交给指纹审计兜底。"""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>')
        lexer.whitespace_split = True
        lexer.commenters = ''
        return list(lexer)
    except ValueError:
        return []


def _operand_path(raw: str, cwd: Path) -> Path | None:
    """解析不含 shell 展开的操作数；动态操作数由 post-Bash 指纹关闭失败。"""
    if not raw or raw == '-' or any(marker in raw for marker in ('$(', '`', '${')):
        return None
    expanded = os.path.expanduser(raw)
    candidate = Path(expanded)
    return candidate if candidate.is_absolute() else cwd / candidate


def primary_write_reason(
    command: str,
    *,
    cwd: Path,
    checkout_root: Path,
    primary_root: Path,
) -> str:
    """识别 linked worktree Bash 对 primary checkout 的常见直接写入。"""
    try:
        if checkout_root.resolve(strict=True) == primary_root.resolve(strict=True):
            return ''
    except OSError:
        return '无法证明 linked worktree 与 primary checkout 身份；禁止 mutation。'
    tokens = _shell_tokens(command)
    if not tokens:
        return ''
    effective_cwd = cwd.resolve(strict=False)
    index = 0
    separators = {'&&', '||', ';', '|', '&'}
    while index < len(tokens):
        if tokens[index] in separators:
            index += 1
            continue
        end = index
        while end < len(tokens) and tokens[end] not in separators:
            end += 1
        segment = tokens[index:end]
        index = end
        if not segment:
            continue
        if segment[0] == 'cd' and len(segment) >= 2:
            candidate = _operand_path(segment[1], effective_cwd)
            if candidate is not None:
                effective_cwd = candidate.resolve(strict=False)
            continue

        # shell 重定向的目标始终是写路径；输入重定向不在此列。
        for position, token in enumerate(segment):
            target = ''
            if token in {'>', '>>', '>|'} and position + 1 < len(segment):
                target = segment[position + 1]
            elif token.startswith(('>', '>>')) and token not in {'>', '>>'}:
                target = token.lstrip('>')
            candidate = _operand_path(target, effective_cwd)
            if candidate is not None and _inside(candidate, primary_root):
                return '禁止 linked worktree 通过 shell redirection 写 primary checkout。'

        executable = Path(segment[0]).name
        args = segment[1:]
        if executable == 'git':
            git_cwd = effective_cwd
            cursor = 0
            while cursor < len(args):
                if args[cursor] == '-C' and cursor + 1 < len(args):
                    candidate = _operand_path(args[cursor + 1], effective_cwd)
                    if candidate is not None:
                        git_cwd = candidate.resolve(strict=False)
                    cursor += 2
                    continue
                if args[cursor].startswith('-'):
                    cursor += 1
                    continue
                break
            verb = args[cursor] if cursor < len(args) else ''
            if _inside(git_cwd, primary_root) and verb not in PRIMARY_GIT_READ_ONLY:
                return f'禁止 linked worktree 通过 git -C primary 执行写操作：{verb or "unknown"}。'
            continue

        destinations: list[str] = []
        plain = [arg for arg in args if arg and not arg.startswith('-')]
        target_option = next(
            (
                args[pos + 1]
                for pos, arg in enumerate(args[:-1])
                if arg in {'-t', '--target-directory'}
            ),
            '',
        )
        target_option = next(
            (arg.split('=', 1)[1] for arg in args if arg.startswith('--target-directory=')),
            target_option,
        )
        if executable in {'cp', 'install'} and target_option:
            destinations = [target_option]
        elif executable == 'mv':
            destinations = plain
        elif executable in {'cp', 'rsync', 'install', 'ln'} and plain:
            destinations = [plain[-1]]
        elif executable == 'sed' and any(arg == '-i' or arg.startswith('-i') for arg in args):
            # sed 表达式可能无法静态区分；把 primary 下的任一操作数视为写目标。
            destinations = plain
        elif executable in {
            'touch',
            'mkdir',
            'rm',
            'rmdir',
            'truncate',
            'chmod',
            'chown',
            'tee',
        }:
            destinations = plain
        for raw in destinations:
            candidate = _operand_path(raw, effective_cwd)
            if candidate is not None and _inside(candidate, primary_root):
                return f'禁止 linked worktree 通过 {executable} 写 primary checkout。'
    return ''


# 判断是否读取 仅 命令。
def is_read_only_command(command: str) -> bool:
    """参数：
        command: 待执行的命令。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    cmd = command.strip()
    if not cmd or WRITE_SHELL_TOKENS.search(cmd) or SHELL_EXPANSION_TOKENS.search(cmd):
        return False
    parts = [part.strip() for part in re.split(r'\s*(?:&&|;)\s*', cmd) if part.strip()]
    if not parts:
        return False
    for part in parts:
        normalized = re.sub(r'\s+', ' ', part)
        if normalized in {'ls', 'pwd'}:
            continue
        if normalized.startswith('cd ') and not re.search(r'[|<>`$()]', normalized):
            continue
        try:
            tokens = shlex.split(normalized)
        except ValueError:
            return False
        if len(tokens) >= 4 and tokens[0] == 'git' and tokens[1] == '-C':
            verb = next((token for token in tokens[3:] if not token.startswith('-')), '')
            if verb in PRIMARY_GIT_READ_ONLY:
                continue
        if (
            tokens
            and tokens[0] == 'find'
            and any(token in {'-delete', '-exec', '-execdir', '-ok', '-okdir'} for token in tokens)
        ):
            return False
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
    assert is_read_only_command('cd /tmp && git status --short')
    assert not is_read_only_command('cd /tmp | python3 scripts/x.py')
    assert not is_read_only_command("git status $(python3 -c 'print(1)')")
    assert not is_read_only_command('python3 scripts/x.py')
    assert not is_read_only_command('sed -n 1p a > b')


if __name__ == '__main__':
    _self_test()
    print('bash_policy self-test PASS')
