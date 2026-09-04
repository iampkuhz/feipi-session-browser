"""检查生产 Python/shell 源码的中文注释、术语和说明完整性。

这项检查保证关键源码说明以中文表达职责和约束。公开入口是 ``check(arguments)``，失败表示
发现必须改写的注释、docstring 或术语策略问题。Java/Kotlin 注释由 Java quality-gates 负责。"""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

from scripts.gates.checks.check_protocol import CheckResult, argument_parser, repository_root

REPO_ROOT = repository_root()


HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
LATIN = re.compile(r'[A-Za-z]')
DIRECTIVE = re.compile(
    r'^(?:SPDX-|Copyright|noinspection|language=|region|endregion|spotless:|formatter:|'
    r'CHECKSTYLE|PMD|ktlint|generated|shellcheck\b|noqa\b|type:\s*ignore\b|pragma:|'
    r'pylint:|ruff:|fmt:|pyright:|mypy:|isort:|flake8:|coding[:=]|-\*-\s*coding)',
    re.I,
)
LOW_INFORMATION = re.compile(
    r'\b(?:TODO|TBD|FIXME|XXX)\b|待补充|以后补|稍后处理|临时注释|'
    r'当前函数使用的输入'
    r'参数|当前函数的计算'
    r'结果|Computed\s+结果|output\s+参数|'
    r'维护\s+project\s+Python\s+cached|表示\s+[A-Za-z_][\w/.-]*\s*[。.]|'
    r'维护\s+[A-Za-z_][\w.-]*\s+(?:函数)?行为|提供\s+[A-Za-z_][\w.-]*\s+脚本能力',
    re.I,
)
ENGLISH_SECTION = re.compile(
    r'^(?:Args|Arguments|Parameters|Returns|Yields|Raises|Examples|Attributes|Notes?):\s*$', re.I
)
URL = re.compile(r'https?://\S+')
HTML = re.compile(r'</?[A-Za-z][^>]*>')
TAG = re.compile(
    r'\{@(?:code|link|linkplain|literal|value)\s+[^}]*}|@(?:param|return|throws|exception|since|see|deprecated)\b'
)
IDENT = re.compile(r'`[^`]+`|\b(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*\b')
CORE_NAME = re.compile(
    r'(?:stop|gate|lock|lease|evidence|receipt|cache|state|transition|hook|fenc|registry|mutation)',
    re.I,
)
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


@dataclass(frozen=True)
class Comment:
    """保存待审计文本的位置与来源类型；不读取文件，由提取器创建。"""

    path: str
    line: int
    kind: str
    text: str


@dataclass(frozen=True)
class Violation:
    """保存单条可操作诊断；不负责格式化，由命令行报告器消费。"""

    path: str
    line: int
    code: str
    message: str
    suggestion: str
    preview: str


def _load_policy(path: Path | None = None) -> tuple[set[str], tuple[str, ...]]:
    """从集中策略加载规范技术术语与禁用翻译，策略缺失或结构错误时 fail-closed。"""
    target = path or REPO_ROOT / 'config' / 'technical-terms.json'
    data = json.loads(target.read_text(encoding='utf-8'))
    terms = data.get('canonical_terms')
    forbidden = data.get('forbidden_translations', [])
    if not isinstance(terms, list) or not terms or not all(isinstance(item, str) for item in terms):
        raise ValueError(f'canonical_terms 必须是非空字符串列表: {target}')
    if not isinstance(forbidden, list) or not all(isinstance(item, str) for item in forbidden):
        raise ValueError(f'forbidden_translations 必须是字符串列表: {target}')
    return set(terms), tuple(forbidden)


def _normalize(text: str, terms: set[str]) -> str:
    """移除指令、标记和集中 allowlist 术语，保留用于语言判定的叙述正文。"""
    lines = []
    for raw in text.splitlines():
        value = re.sub(r'^\s*\*?\s?', '', raw).strip()
        if value and not DIRECTIVE.match(value):
            lines.append(value)
    value = IDENT.sub(' ', TAG.sub(' ', HTML.sub(' ', URL.sub(' ', ' '.join(lines)))))
    for term in sorted(terms, key=len, reverse=True):
        value = re.sub(
            rf'(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])', ' ', value, flags=re.I
        )
    return re.sub(r'\s+', ' ', value).strip()


def _check_comment(
    comment: Comment, terms: set[str], forbidden: tuple[str, ...]
) -> list[Violation]:
    """检查一段叙述文本的术语、信息量和中文主体，不决定该位置是否必须有说明。"""
    raw = comment.text.strip()
    first = re.sub(r'^\s*\*?\s?', '', raw.splitlines()[0]).strip() if raw else ''
    if not raw or DIRECTIVE.match(first):
        return []
    for word in forbidden:
        if word in raw:
            return [
                Violation(
                    comment.path,
                    comment.line,
                    'TECH_TERM_NOT_CANONICAL',
                    f'技术术语必须使用集中策略中的规范写法，发现“{word}”',
                    '替换为 config/technical-terms.json 中的 canonical_terms 写法',
                    first[:160],
                )
            ]
    if LOW_INFORMATION.search(raw):
        return [
            Violation(
                comment.path,
                comment.line,
                'COMMENT_LOW_INFORMATION',
                '说明包含参数复述、占位语或机械模板',
                '删除简单 helper 的废话；核心接口改写为职责、边界或失败语义',
                first[:160],
            )
        ]
    value = _normalize(raw, terms)
    if not value or not (HAN.search(value) or LATIN.search(value)):
        return []
    han_count = len(HAN.findall(value))
    latin_count = len(LATIN.findall(value))
    ratio = han_count / max(1, han_count + latin_count)
    min_han = 2 if comment.kind.endswith('line') else 4
    violations: list[Violation] = []
    min_ratio = 0.12
    if han_count < min_han or ratio < min_ratio:
        violations.append(
            Violation(
                comment.path,
                comment.line,
                'COMMENT_NOT_CHINESE_DOMINANT',
                f'中文不是说明主体（Han={han_count}, Latin={latin_count}, ratio={ratio:.3f}）',
                '使用中文解释职责或约束；仅保留 allowlist 中必要技术术语',
                first[:160],
            )
        )
    english_words = re.findall(r'\b[A-Za-z]{3,}\b', value)
    if han_count < 6 and len(english_words) >= 3:
        violations.append(
            Violation(
                comment.path,
                comment.line,
                'COMMENT_MECHANICAL_MIXED_LANGUAGE',
                '说明使用中文前缀包裹英文主体或机械中英混排',
                '把英文句子改为中文，仅保留集中 allowlist 中的术语',
                first[:160],
            )
        )
    return violations


def _docstring_comment(path: Path, node: ast.AST, kind: str) -> Comment | None:
    """返回 AST 节点的原始 docstring 及精确起始行；节点没有 docstring 时返回空。"""
    body = getattr(node, 'body', None)
    if (
        not body
        or not isinstance(body[0], ast.Expr)
        or not isinstance(body[0].value, ast.Constant)
        or not isinstance(body[0].value.value, str)
    ):
        return None
    return Comment(str(path), body[0].lineno, kind, body[0].value.value)


def _docstring_violations(
    comment: Comment, terms: set[str], forbidden: tuple[str, ...]
) -> list[Violation]:
    """逐段检查标准 Python docstring，并给英文段落标题精确定位。"""
    violations = _check_comment(comment, terms, forbidden)
    for offset, raw in enumerate(comment.text.splitlines()):
        value = raw.strip()
        if ENGLISH_SECTION.match(value):
            violations.append(
                Violation(
                    comment.path,
                    comment.line + offset,
                    'DOCSTRING_ENGLISH_SECTION_LABEL',
                    'docstring 段落标题必须使用中文',
                    '改用“参数/返回/异常/示例/说明”',
                    value,
                )
            )
    return violations


def _required_definition(node: ast.AST) -> bool:
    """仅选择 public、CLI main 与安全关键 private，避免强迫简单 private helper 写废话。"""
    name = getattr(node, 'name', '')
    return bool(name and (not name.startswith('_') or CORE_NAME.search(name)))


def _is_check_leaf(path: Path) -> bool:
    """判断文件是否位于领域目录并使用统一 `check_*.py` 命名。"""
    normalized = path.as_posix()
    return (
        normalized.startswith('scripts/gates/checks/') or '/scripts/gates/checks/' in normalized
    ) and path.name.startswith('check_')


def _module_contract_missing(path: Path, text: str) -> list[str]:
    """按领域 Check 或普通模块各自的首屏说明约定报告缺失信息。"""
    if _is_check_leaf(path):
        missing = []
        if not re.search(r'检查|验证|审计|核对|检测', text):
            missing.append('检查对象')
        if not re.search(
            r'避免|防止|阻止|确保|保证|证明|保持|降低|以便|帮助|用于|原因|需要|必须|会|因此',
            text,
        ):
            missing.append('存在原因')
        if not re.search(r'(?:公开|唯一|唯一公开)\s*入口.{0,60}check', text, re.S | re.I):
            missing.append('公开入口')
        if not re.search(r'失败|诊断|错误|违规|不满足', text):
            missing.append('失败含义')
        return missing

    # 非 Check 模块仍说明职责边界和调用位置，避免把领域模板强加给基础设施。
    missing = []
    if not re.search(
        r'负责|用于|检查|验证|解析|定义|登记|提供|执行|运行|判定|持久化|生成|统一|维护|审计',
        text,
    ):
        missing.append('职责')
    if not re.search(
        r'不负责|不承担|不包含|不得|只(?:负责|执行|提供|读取|写入|保存|委托|适配|检查|验证|生成|暴露)',
        text,
    ):
        missing.append('非职责')
    if not re.search(
        r'调用|入口|命令行|CLI|Hook|Stop|Gate|脚本|pipeline|executor|runtime|维护者', text, re.I
    ):
        missing.append('调用者')
    return missing


def _check_python_file(path: Path, terms: set[str], forbidden: tuple[str, ...]) -> list[Violation]:
    """审计 Python module/public/core docstring 与真实 token 注释，不扫描字符串中的井号。"""
    text = path.read_text(encoding='utf-8')
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                str(path),
                exc.lineno or 1,
                'PYTHON_SYNTAX_ERROR',
                exc.msg,
                '先修复 Python 语法，再运行注释 Gate',
                '',
            )
        ]
    violations: list[Violation] = []
    module_doc = _docstring_comment(path, tree, 'module-doc')
    if module_doc is None:
        suggestion = (
            '添加中文说明：检查什么、为什么需要、公开入口和失败表示什么'
            if _is_check_leaf(path)
            else '在 shebang/未来导入之前添加职责、非职责和调用者说明'
        )
        violations.append(
            Violation(
                str(path),
                1,
                'MODULE_DOCSTRING_MISSING',
                '生产模块缺少中文职责说明',
                suggestion,
                path.name,
            )
        )
    else:
        violations.extend(_docstring_violations(module_doc, terms, forbidden))
        missing = _module_contract_missing(path, module_doc.text)
        if missing:
            suggestion = (
                '依次说明检查什么、为什么需要、公开入口和失败表示什么'
                if _is_check_leaf(path)
                else '说明本模块负责什么、不负责什么、由哪个入口或运行阶段调用'
            )
            violations.append(
                Violation(
                    str(path),
                    module_doc.line,
                    'MODULE_DOCSTRING_INCOMPLETE',
                    f'模块说明缺少：{"、".join(missing)}',
                    suggestion,
                    module_doc.text.splitlines()[0][:160],
                )
            )
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = _docstring_comment(path, node, 'definition-doc')
        if _required_definition(node) and doc is None:
            violations.append(
                Violation(
                    str(path),
                    node.lineno,
                    'DEFINITION_DOCSTRING_MISSING',
                    f'{node.name} 缺少标准中文 docstring',
                    '在定义体首行说明职责与关键边界；简单 private helper 无需补充',
                    node.name,
                )
            )
        if doc is not None:
            violations.extend(_docstring_violations(doc, terms, forbidden))
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            value = token.string[1:].strip()
            if (
                not value
                or (token.start[0] == 1 and token.string.startswith('#!'))
                or DIRECTIVE.match(value)
            ):
                continue
            if re.search(r'[A-Za-z㐀-䶿一-鿿豈-﫿]', value):
                violations.extend(
                    _check_comment(
                        Comment(str(path), token.start[0], 'script-line', value), terms, forbidden
                    )
                )
    except tokenize.TokenError:
        pass
    return violations


def _extract_script_comments(path: Path) -> list[Comment]:
    """提取 shell 叙述注释；不把 shebang、工具指令或纯分隔符作为说明。"""
    comments = []
    for lineno, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        stripped = raw.lstrip()
        if not stripped.startswith('#') or stripped.startswith('#!'):
            continue
        value = stripped[1:].strip()
        if value and not DIRECTIVE.match(value) and re.search(r'[A-Za-z㐀-䶿一-鿿豈-﫿]', value):
            comments.append(Comment(str(path), lineno, 'script-line', value))
    return comments


def _check_shell_file(path: Path, terms: set[str], forbidden: tuple[str, ...]) -> list[Violation]:
    """审计 shell 说明；Hook wrapper 还必须明确委托边界，普通内部函数不强制逐个注释。"""
    comments = _extract_script_comments(path)
    violations = [
        item for comment in comments for item in _check_comment(comment, terms, forbidden)
    ]
    if '/hooks/' in f'/{path.as_posix()}':
        header = [comment for comment in comments if comment.line <= 8]
        if not header:
            violations.append(
                Violation(
                    str(path),
                    1,
                    'HOOK_WRAPPER_DOC_MISSING',
                    'Hook wrapper 缺少中文委托说明',
                    '说明平台事件、共享 runtime 委托和本文件不承载的业务逻辑',
                    path.name,
                )
            )
        elif not re.search(r'委托|转发|调用', ' '.join(comment.text for comment in header)):
            violations.append(
                Violation(
                    str(path),
                    header[0].line,
                    'HOOK_WRAPPER_DOC_INCOMPLETE',
                    'Hook wrapper 未说明委托关系',
                    '明确 payload 转交给哪个共享入口，并说明包装器不实现业务策略',
                    header[0].text[:160],
                )
            )
    return violations


def _discover(values: list[str]) -> list[Path]:
    """在显式根目录下发现 Python/shell 源码，并排除生成物与依赖目录。"""
    suffixes = {'.py', '.sh'}
    result: set[Path] = set()
    for raw in values:
        path = Path(raw)
        if path.is_file() and path.suffix in suffixes:
            result.add(path)
        elif path.is_dir():
            for candidate in path.rglob('*'):
                if (
                    candidate.is_file()
                    and candidate.suffix in suffixes
                    and not set(candidate.parts) & EXCLUDED_PARTS
                ):
                    result.add(candidate)
    return sorted(result, key=lambda item: item.as_posix())


def check(arguments: list[str]) -> CheckResult:
    """解析统一入口参数，返回 Python/shell 注释违规诊断。"""
    parser = argument_parser(description='Python/shell 生产源码中文注释契约检查器')
    parser.add_argument(
        'paths',
        nargs='*',
        default=['scripts'],
    )
    parser.add_argument('--policy', default=str(REPO_ROOT / 'config' / 'technical-terms.json'))
    args = parser.parse_args(arguments)
    try:
        terms, forbidden = _load_policy(Path(args.policy))
    except OSError as exc:
        return CheckResult.execution_failure(
            [f'{args.policy}:1: POLICY_UNAVAILABLE: {exc}'], reason='input-unavailable'
        )
    except (ValueError, json.JSONDecodeError) as exc:
        return CheckResult.from_errors(
            [f'{args.policy}:1: POLICY_INVALID: {exc}: suggestion=修复集中术语策略后重试']
        )
    all_violations: list[Violation] = []
    try:
        for path in _discover(args.paths):
            if path.suffix == '.py':
                all_violations.extend(_check_python_file(path, terms, forbidden))
            else:
                all_violations.extend(_check_shell_file(path, terms, forbidden))
    except OSError as exc:
        return CheckResult.execution_failure([f'源码读取失败: {exc}'], reason='input-unavailable')
    all_violations.sort(key=lambda item: (item.path, item.line, item.code))
    return CheckResult.from_errors(
        (
            f'{item.path}:{item.line}: {item.code}: {item.message}: suggestion={item.suggestion}: {item.preview}'
        )
        for item in all_violations
    )
