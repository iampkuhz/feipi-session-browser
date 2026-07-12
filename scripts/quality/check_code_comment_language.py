#!/usr/bin/env python3
"""词法级中文注释检查器：近似验证代码注释以中文为主体。"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered

# 触发模式：当变更文件匹配这些 pattern 时才运行检查。
TRIGGER_PATTERNS = [
    'java/**/src/main/java/**/*.java',
    'java/**/src/test/java/**/*.java',
    '**/*.java',
]

# ============================================================
# 正则与内置术语表
# ============================================================
HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
LATIN = re.compile(r'[A-Za-z]')
PLACEHOLDER = re.compile(
    r'\b(?:TODO|TBD|FIXME|XXX)\b|待补充|以后补|稍后处理|临时注释|此处保留必要英文术语',
    re.I,
)
DIRECTIVE = re.compile(
    r'^(?:SPDX-|Copyright|noinspection|language=|region|endregion|'
    r'spotless:|formatter:|CHECKSTYLE|PMD|ktlint|generated|'
    r'shellcheck\b|noqa\b|type:\s*ignore\b|pragma:|pylint:|ruff:|fmt:|'
    r'pyright:|mypy:|isort:|flake8:|coding[:=]|-\*-\s*coding)',
    re.I,
)
URL = re.compile(r'https?://\S+')
HTML = re.compile(r'</?[A-Za-z][^>]*>')
TAG = re.compile(
    r'\{@(?:code|link|linkplain|literal|value)\s+[^}]*}'
    r'|@(?:param|return|throws|exception|since|see|deprecated)\b'
)
IDENT = re.compile(r'`[^`]+`|\b(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*\b')
SHELL_FUNCTION = re.compile(
    r'^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_-]*)\s*(?:\(\))?\s*\{'
)
DOCSTRING_ENGLISH_LABEL = re.compile(
    r'^(?:Args|Arguments|Parameters|Returns|Yields|Raises|Examples|Attributes|Note|Notes):\s*$'
)
DOCSTRING_CHINESE_LABEL = re.compile(r'^(?:参数|返回|异常|示例|说明)[:：]\s*$')
CHINESE_SECTION_LABEL = re.compile(r'^(?:参数|返回|异常|示例|说明)[:：]$')

TERMS: set[str] = {
    'Java',
    'JVM',
    'Gradle',
    'Kotlin',
    'DSL',
    'JUnit',
    'Javadoc',
    'DocLint',
    'JSON',
    'JSONL',
    'NDJSON',
    'SQLite',
    'Jackson',
    'Picocli',
    'API',
    'CLI',
    'record',
    'enum',
    'sealed',
    'interface',
    'token',
    'tool',
    'agent',
    'session',
    'SHA',
    'UTF',
    'stdout',
    'stderr',
    'fixture',
    'artifact',
    'schema',
    'hash',
    'ID',
    'UUID',
    'HTTP',
    'SQL',
    'Git',
    'Python',
    'Bash',
    'shell',
    'hook',
    'hooks',
    'Stop',
    'PreToolUse',
    'PostToolUse',
    'SubagentStop',
    'OpenSpec',
    'Qoder',
    'Codex',
    'Claude',
    'pytest',
    'Ruff',
    'Pyright',
    'MCP',
}

# 排除的目录片段
EXCLUDED_PARTS = {
    'build',
    '.gradle',
    'generated',
    'gen',
    'third_party',
    'vendor',
    'node_modules',
    '__pycache__',
    'tmp',
}


# ============================================================
# 数据结构
# ============================================================
@dataclass(frozen=True)
class Comment:
    """表示 Comment。

    属性：
        path: 待检查的路径。
        line: 待检查的源码行。
        kind: kind 参数。
        text: 待检查的文本。
    """

    path: str
    line: int
    kind: str
    text: str


@dataclass(frozen=True)
class Violation:
    """表示一条 Violation 检查发现。

    属性：
        path: 待检查的路径。
        line: 待检查的源码行。
        code: code 参数。
        message: 用户可读消息。
        preview: preview 参数。
    """

    path: str
    line: int
    code: str
    message: str
    preview: str


# ============================================================
# 注释提取 — 词法状态机
# ============================================================
# 提取源码注释。
def extract(path: Path) -> list[Comment]:
    """参数：
        path: 待检查的路径。

    返回：
        结果列表。
    """
    text = path.read_text(encoding='utf-8')
    out: list[Comment] = []
    i = 0
    n = len(text)
    state = 'normal'
    start = 0
    depth = 0

    # 计算源码行号。
    def line(pos: int) -> int:
        """参数：
            pos: pos 参数。

        返回：
            进程退出码。
        """
        return text.count('\n', 0, pos) + 1

    while i < n:
        if state == 'normal':
            if text.startswith('"""', i):
                state = 'text'
                i += 3
            elif text[i] == '"':
                state = 'string'
                i += 1
            elif text[i] == "'":
                state = 'char'
                i += 1
            elif text.startswith('//', i):
                start = i
                state = 'line'
                i += 2
            elif text.startswith('/*', i):
                start = i
                depth = 1
                state = 'block'
                i += 2
            else:
                i += 1
        elif state in ('string', 'char'):
            end = '"' if state == 'string' else "'"
            if text[i] == '\\':
                i += 2
            elif text[i] == end:
                state = 'normal'
                i += 1
            else:
                i += 1
        elif state == 'text':
            if text.startswith('"""', i):
                state = 'normal'
                i += 3
            else:
                i += 1
        elif state == 'line':
            if text[i] == '\n':
                out.append(Comment(str(path), line(start), 'line', text[start + 2 : i]))
                state = 'normal'
            i += 1
        elif state == 'block':
            if text.startswith('/*', i):
                depth += 1
                i += 2
            elif text.startswith('*/', i):
                depth -= 1
                i += 2
                if depth == 0:
                    kind = 'javadoc' if text.startswith('/**', start) else 'block'
                    out.append(Comment(str(path), line(start), kind, text[start + 2 : i - 2]))
                    state = 'normal'
            else:
                i += 1

    if state == 'line':
        out.append(Comment(str(path), line(start), 'line', text[start + 2 :]))
    return out


# 提取脚本 注释。
def extract_script_comments(path: Path) -> list[Comment]:
    """参数：
        path: 待检查的路径。

    返回：
        结果列表。
    """
    comments: list[Comment] = []
    for lineno, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        stripped = raw.lstrip()
        if not stripped.startswith('#'):
            continue
        if lineno == 1 and stripped.startswith('#!'):
            continue
        text = stripped[1:].strip()
        if not text:
            continue
        if DIRECTIVE.match(text):
            continue
        if CHINESE_SECTION_LABEL.match(text):
            continue
        # 仅由分隔符组成的段落边界不是叙述性注释。
        if not re.search(r'[A-Za-z㐀-䶿一-鿿豈-﫿]', text):
            continue
        comments.append(Comment(str(path), lineno, 'script-line', text))
    return comments


# 从单行文本中提取可检查的脚本注释。
def _script_comment_from_line(path: Path, line_no: int, raw: str) -> Comment | None:
    """参数：
        path: 待检查的路径。
        line_no: 源码行号。
        raw: 原始输入文本。

    返回：
        可检查的脚本注释；该行不属于叙述性注释时返回 None。
    """
    stripped = raw.lstrip()
    if not stripped.startswith('#') or stripped.startswith('#!'):
        return None
    text = stripped[1:].strip()
    if not text or DIRECTIVE.match(text):
        return None
    if CHINESE_SECTION_LABEL.match(text):
        return None
    if not re.search(r'[A-Za-z㐀-䶿一-鿿豈-﫿]', text):
        return None
    return Comment(str(path), line_no, 'script-line', text)


# 提取 HTML/Jinja 模板注释。
def extract_template_comments(path: Path) -> list[Comment]:
    """参数：
        path: 待检查的模板路径。

    返回：
        模板注释列表。
    """
    text = path.read_text(encoding='utf-8')
    comments: list[Comment] = []
    for pattern, kind in ((r'<!--(.*?)-->', 'html-comment'), (r'\{#(.*?)#\}', 'jinja-comment')):
        for match in re.finditer(pattern, text, re.DOTALL):
            body = match.group(1).strip()
            if not body:
                continue
            line_no = text.count('\n', 0, match.start()) + 1
            comments.append(Comment(str(path), line_no, kind, body))
    return comments


# 查找函数定义前最近的叙述性注释。
def _previous_narrative_comment(path: Path, lines: list[str], index: int) -> Comment | None:
    """参数：
        path: 待检查的路径。
        lines: 待检查的源码行列表。
        index: 开始向上查找的源码行下标。

    返回：
        最近的叙述性注释；没有找到时返回 None。
    """
    idx = index
    while idx >= 0:
        raw = lines[idx]
        if not raw.strip():
            idx -= 1
            continue
        stripped = raw.lstrip()
        if not stripped.startswith('#'):
            return None
        comment = _script_comment_from_line(path, idx + 1, raw)
        if comment is not None:
            return comment
        idx -= 1
    return None


# 查找 Python 函数定义前的说明注释。
def _previous_comment_for_python_function(
    path: Path,
    lines: list[str],
    lineno: int,
) -> Comment | None:
    """参数：
        path: 待检查的路径。
        lines: 待检查的源码行列表。
        lineno: Python 函数定义所在行号。

    返回：
        函数上方的说明注释；没有找到时返回 None。
    """
    idx = lineno - 2
    while idx >= 0 and not lines[idx].strip():
        idx -= 1
    while idx >= 0 and lines[idx].lstrip().startswith('@'):
        idx -= 1
        while idx >= 0 and not lines[idx].strip():
            idx -= 1
    return _previous_narrative_comment(path, lines, idx)


# 查找 shell 函数定义前的说明注释。
def _previous_comment_for_shell_function(
    path: Path,
    lines: list[str],
    index: int,
) -> Comment | None:
    """参数：
        path: 待检查的路径。
        lines: 待检查的源码行列表。
        index: shell 函数定义所在行下标。

    返回：
        函数上方的说明注释；没有找到时返回 None。
    """
    idx = index - 1
    while idx >= 0 and not lines[idx].strip():
        idx -= 1
    return _previous_narrative_comment(path, lines, idx)


# 检查脚本函数的中文注释布局。
def check_function_comments(
    path: Path,
    terms: set[str],
    forbidden: tuple[str, ...],
) -> list[Violation]:
    """参数：
        path: 待检查的路径。
        terms: 允许保留英文的规范技术术语集合。
        forbidden: 禁止出现的非规范技术术语翻译。

    返回：
        函数注释布局和语言质量违规列表。
    """
    violations: list[Violation] = []
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    if path.suffix == '.py':
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            return violations
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            comment = _previous_comment_for_python_function(path, lines, node.lineno)
            if comment is None:
                violations.append(
                    Violation(
                        str(path),
                        node.lineno,
                        'FUNCTION_COMMENT_MISSING',
                        '函数说明必须放在 def 上方',
                        node.name,
                    )
                )
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                doc_line = node.body[0].lineno if node.body else node.lineno
                doc_comment = Comment(
                    str(path),
                    doc_line,
                    'function-doc',
                    docstring,
                )
                doc_violations = check(doc_comment, terms, forbidden)
                doc_violations.extend(
                    check_docstring_lines(
                        doc_comment,
                        terms,
                        forbidden,
                    )
                )
                doc_violations.extend(check_docstring_layout(doc_comment))
                violations.extend(doc_violations)
            elif _python_function_needs_detail_doc(node):
                violations.append(
                    Violation(
                        str(path),
                        node.lineno,
                        'FUNCTION_DETAIL_MISSING',
                        '参数和返回值说明必须放在 def 内开头 docstring',
                        node.name,
                    )
                )
        return violations

    if path.suffix == '.sh':
        for index, raw in enumerate(lines):
            match = SHELL_FUNCTION.match(raw)
            if not match:
                continue
            comment = _previous_comment_for_shell_function(path, lines, index)
            if comment is None:
                violations.append(
                    Violation(
                        str(path),
                        index + 1,
                        'FUNCTION_COMMENT_MISSING',
                        '函数缺少中文注释',
                        match.group(1),
                    )
                )
    return violations


# 判断 Python 函数是否需要函数内参数或返回值说明。
def _python_function_needs_detail_doc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """参数：
        node: 待检查的 Python 函数 AST 节点。

    返回：
        存在业务参数或显式非 None 返回值时返回 true。
    """
    args = (
        list(node.args.posonlyargs)
        + list(node.args.args)
        + list(node.args.kwonlyargs)
    )
    if any(arg.arg not in {'self', 'cls'} for arg in args):
        return True
    if node.args.vararg or node.args.kwarg:
        return True
    if node.returns is None:
        return False
    try:
        return ast.unparse(node.returns) != 'None'
    except Exception:
        return True


# 检查docstring 布局。
def check_docstring_layout(comment: Comment) -> list[Violation]:
    """参数：
        comment: 函数开头的 docstring 注释。

    返回：
        docstring 布局违规列表。
    """
    for offset, raw in enumerate(comment.text.splitlines()):
        value = raw.strip()
        if not value:
            continue
        if DOCSTRING_CHINESE_LABEL.match(value) or CHINESE_SECTION_LABEL.match(value):
            return []
        return [
            Violation(
                comment.path,
                comment.line + offset,
                'FUNCTION_DOCSTRING_SUMMARY_IN_BODY',
                '函数说明放在 def 上方，def 内 docstring 只写参数、返回值、异常或示例',
                value[:160],
            )
        ]
    return []


# 检查docstring 行。
def check_docstring_lines(
    comment: Comment,
    terms: set[str],
    forbidden: tuple[str, ...],
) -> list[Violation]:
    """参数：
        comment: comment 参数。
        terms: terms 参数。
        forbidden: forbidden 参数。

    返回：
        结果列表。
    """
    violations: list[Violation] = []
    for offset, raw in enumerate(comment.text.splitlines()):
        value = raw.strip()
        if not value:
            continue
        if DOCSTRING_CHINESE_LABEL.match(value):
            continue
        if CHINESE_SECTION_LABEL.match(value):
            continue
        if DOCSTRING_ENGLISH_LABEL.match(value):
            violations.append(
                Violation(
                    comment.path,
                    comment.line + offset,
                    'DOCSTRING_ENGLISH_SECTION_LABEL',
                    'docstring 段落标题必须使用中文',
                    value,
                )
            )
            continue
        line_violations = check(
            Comment(
                comment.path,
                comment.line + offset,
                'function-doc-line',
                value,
            ),
            terms,
            forbidden,
        )
        violations.extend(line_violations)
    return violations


# 规范化注释文本。
def normalize(text: str, terms: set[str]) -> str:
    """参数：
        text: 待检查的文本。
        terms: terms 参数。

    返回：
        normalize 字符串。
    """
    lines = []
    for raw in text.splitlines():
        value = re.sub(r'^\s*\*?\s?', '', raw).strip()
        if not value or DIRECTIVE.match(value):
            continue
        lines.append(value)
    value = ' '.join(lines)
    value = URL.sub(' ', value)
    value = HTML.sub(' ', value)
    value = TAG.sub(' ', value)
    value = IDENT.sub(' ', value)
    for term in sorted(terms, key=len, reverse=True):
        value = re.sub(
            rf'(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])',
            ' ',
            value,
            flags=re.I,
        )
    return re.sub(r'\s+', ' ', value).strip()


# 维护检查。
def check(comment: Comment, terms: set[str], forbidden: tuple[str, ...]) -> list[Violation]:
    """参数：
        comment: comment 参数。
        terms: terms 参数。
        forbidden: forbidden 参数。

    返回：
        结果列表。
    """
    raw = comment.text.strip()
    first = re.sub(r'^\s*\*?\s?', '', raw.splitlines()[0]).strip() if raw else ''
    if not raw or DIRECTIVE.match(first):
        return []

    # 检查禁止的非规范翻译
    for word in forbidden:
        if word in raw:
            return [
                Violation(
                    comment.path,
                    comment.line,
                    'TECH_TERM_NOT_CANONICAL',
                    f'技术术语应使用约定英文，禁止：{word}',
                    first[:160],
                )
            ]

    # 检查占位/低信息注释
    if PLACEHOLDER.search(raw):
        return [
            Violation(
                comment.path,
                comment.line,
                'COMMENT_LOW_INFORMATION',
                '注释包含占位或低信息表达',
                first[:160],
            )
        ]

    value = normalize(raw, terms)
    if not value or not (HAN.search(value) or LATIN.search(value)):
        return []

    han_count = len(HAN.findall(value))
    latin_count = len(LATIN.findall(value))
    line_like = comment.kind in {'line', 'script-line', 'function-doc-line'}
    min_han = 2 if line_like else 4
    min_ratio = 0.08 if line_like else 0.12
    ratio = han_count / max(1, han_count + latin_count)

    violations: list[Violation] = []
    if han_count < min_han or ratio < min_ratio:
        violations.append(
            Violation(
                comment.path,
                comment.line,
                'COMMENT_NOT_CHINESE_DOMINANT',
                f'Han={han_count}, Latin={latin_count}, ratio={ratio:.3f}',
                first[:160],
            )
        )
    if comment.kind in {'script-line', 'function-doc-line'}:
        semantic = re.sub(r'^说明[:：]\s*', '', raw)
        # 移除中文前缀后再次计算主体语言，避免用“说明：”包裹英文。
        semantic_value = normalize(semantic, terms)
        semantic_han = len(HAN.findall(semantic_value))
        semantic_latin_words = re.findall(r'\b[A-Za-z]{3,}\b', semantic_value)
        if semantic_han < 4 and len(semantic_latin_words) >= 3:
            violations.append(
                Violation(
                    comment.path,
                    comment.line,
                    'COMMENT_ENGLISH_FRAGMENT',
                    '注释不得用中文前缀包裹英文说明',
                    first[:160],
                )
            )
    if '{@inheritDoc}' in raw and han_count < 4:
        violations.append(
            Violation(
                comment.path,
                comment.line,
                'INHERITDOC_WITHOUT_CHINESE',
                '不能只使用 inheritDoc 代替中文说明',
                first[:160],
            )
        )
    return violations


# ============================================================
# 文件发现
# ============================================================
# 发现待扫描文件。
def discover(values: list[str], *, script_comments: bool = False) -> list[Path]:
    """参数：
        values: values 参数。
        script_comments: 是否启用脚本注释扫描。

    返回：
        结果列表。
    """
    suffixes = (
        {'.py', '.sh', '.js', '.css', '.html'}
        if script_comments
        else {'.java', '.kt', '.kts'}
    )
    result: set[Path] = set()
    for raw in values:
        p = Path(raw)
        if p.is_file() and p.suffix in suffixes:
            result.add(p)
        elif p.is_dir():
            patterns = (
                ('*.py', '*.sh', '*.js', '*.css', '*.html')
                if script_comments
                else ('*.java', '*.kt', '*.kts')
            )
            for ext in patterns:
                result.update(x for x in p.rglob(ext) if not (set(x.parts) & EXCLUDED_PARTS))
    return sorted(result, key=lambda x: x.as_posix())


# 判断是否under。
def _is_under(path: Path, root: Path) -> bool:
    """参数：
        path: 待检查的路径。
        root: 扫描根目录。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# 过滤changed-files 路径。
def filter_changed_paths(values: list[str], changed_files: list[str]) -> list[str]:
    """参数：
        values: values 参数。
        changed_files: 待检查的文件列表。

    返回：
        结果列表。
    """
    roots = [Path(raw) for raw in values]
    result: list[str] = []
    seen: set[str] = set()
    for raw in changed_files:
        path = Path(raw)
        if any(path == root or _is_under(path, root) for root in roots):
            normalized = path.as_posix()
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result


# ============================================================
# 主入口
# ============================================================
# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    ap = argparse.ArgumentParser(
        description='词法级中文注释检查器',
    )
    ap.add_argument(
        'paths',
        nargs='*',
        default=['java', 'build-logic', 'build.gradle.kts', 'settings.gradle.kts'],
    )
    ap.add_argument('--jobs', default='auto')
    ap.add_argument('--policy', help='JSON 术语策略文件路径')
    ap.add_argument('--json-report', help='JSON 报告输出路径')
    ap.add_argument('--cache', help='增量缓存路径')
    ap.add_argument('--files-from', help='从 JSON 文件读取要扫描的路径列表')
    ap.add_argument(
        '--script-comments',
        action='store_true',
        help='扫描 shell/Python 脚本的独立 # 注释',
    )
    ap.add_argument(
        '--changed-files-env',
        help='从指定环境变量读取 JSON changed-files，并只扫描相交脚本',
    )
    add_changed_files_arg(ap)
    a = ap.parse_args()

    # 自感知跳过：变更文件不匹配触发模式时直接 SKIP。
    changed_files = parse_changed_files(getattr(a, 'changed_files', None))
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    terms = set(TERMS)
    forbidden: tuple[str, ...] = ()
    if a.policy:
        data = json.loads(Path(a.policy).read_text(encoding='utf-8'))
        terms.update(data.get('canonical_terms', []))
        forbidden = tuple(data.get('forbidden_translations', []))

    paths = a.paths
    if a.files_from:
        files_from_path = Path(a.files_from)
        if files_from_path.exists():
            raw = files_from_path.read_text(encoding='utf-8').strip()
            try:
                parsed = json.loads(raw) if raw.startswith('[') else raw.splitlines()
                paths = [x.strip() for x in parsed if x.strip()]
            except json.JSONDecodeError:
                paths = [x.strip() for x in raw.splitlines() if x.strip()]

    if a.changed_files_env:
        raw_changed = os.environ.get(a.changed_files_env, '').strip()
        try:
            parsed_changed = json.loads(raw_changed) if raw_changed else []
        except json.JSONDecodeError:
            parsed_changed = []
        if isinstance(parsed_changed, list):
            paths = filter_changed_paths(paths, [x for x in parsed_changed if isinstance(x, str)])
        else:
            paths = []

    files = discover(paths, script_comments=a.script_comments)
    jobs = (
        min(16, max(1, os.cpu_count() or 1), max(1, len(files)))
        if a.jobs == 'auto'
        else max(1, int(a.jobs))
    )

    # 增量缓存
    policy_hash = hashlib.sha256(
        json.dumps(sorted(terms)).encode() + json.dumps(sorted(forbidden)).encode() + b'checker-v1'
    ).hexdigest()
    cache: dict = {'policy_hash': policy_hash, 'entries': {}}
    if a.cache:
        cache_path = Path(a.cache)
        if cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text(encoding='utf-8'))
                if loaded.get('policy_hash') == policy_hash:
                    cache = loaded
            except Exception:
                pass

    # 扫描目标文件。
    def scan(path: Path) -> tuple[str, str, list[Violation]]:
        """参数：
            path: 待检查的路径。

        返回：
            结果 tuple。
        """
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = path.as_posix()
        old = cache.get('entries', {}).get(key)
        if old and old.get('sha256') == digest:
            return str(path), digest, [Violation(**x) for x in old.get('violations', [])]
        violations: list[Violation] = []
        if a.script_comments and path.suffix in {'.py', '.sh'}:
            comments = extract_script_comments(path)
        elif a.script_comments and path.suffix == '.html':
            comments = extract_template_comments(path)
        else:
            comments = extract(path)
        for c in comments:
            violations.extend(check(c, terms, forbidden))
        if a.script_comments and path.suffix in {'.py', '.sh'}:
            violations.extend(check_function_comments(path, terms, forbidden))
        return str(path), digest, violations

    all_violations: list[Violation] = []
    entries: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for path_str, digest, vs in pool.map(scan, files):
            all_violations.extend(vs)
            entries[path_str] = {
                'sha256': digest,
                'violations': [asdict(v) for v in vs],
            }

    all_violations.sort(key=lambda v: (v.path, v.line, v.code, v.preview))

    # 写入缓存
    if a.cache:
        cache_out = Path(a.cache)
        cache_out.parent.mkdir(parents=True, exist_ok=True)
        cache_out.write_text(
            json.dumps(
                {'policy_hash': policy_hash, 'entries': dict(sorted(entries.items()))},
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )

    # 写入 JSON 报告
    if a.json_report:
        target = Path(a.json_report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    'files': len(files),
                    'violations': [asdict(v) for v in all_violations],
                },
                ensure_ascii=False,
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )

    for v in all_violations:
        print(f'{v.path}:{v.line}: {v.code}: {v.message}: {v.preview}')

    if all_violations:
        return 1
    print(f'PASS: scanned {len(files)} files with {jobs} workers')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
