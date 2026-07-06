#!/usr/bin/env python3
"""检查 Java record component 是否都有中文 Javadoc 说明。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HAN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
IDENT = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')
QUALIFIED_IDENT = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*(?:\s*\.\s*[A-Za-z_$][A-Za-z0-9_$]*)*')
JAVA_MODIFIERS = {
    'public',
    'protected',
    'private',
    'abstract',
    'static',
    'final',
    'strictfp',
    'sealed',
    'non-sealed',
}
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
class JavadocBlock:
    """表示源码中的一个 Javadoc 注释块。

    属性：
        start: 注释起始字符偏移。
        end: 注释结束字符偏移。
        line: 注释起始行号。
        text: 注释原文。
    """

    start: int
    end: int
    line: int
    text: str


@dataclass(frozen=True)
class RecordDecl:
    """表示 Java record 声明。

    属性：
        name: record 类型名称。
        line: record 关键字所在行号。
        start: record 关键字字符偏移。
        components: component 名称到声明行号的映射。
    """

    name: str
    line: int
    start: int
    components: dict[str, int]


@dataclass(frozen=True)
class Violation:
    """表示 record component Javadoc 违规。

    属性：
        path: 源文件路径。
        line: 源码行号。
        code: 违规代码。
        message: 用户可读说明。
    """

    path: str
    line: int
    code: str
    message: str


# 执行源码解析辅助逻辑。
def _line(text: str, pos: int) -> int:
    """参数：
        text: 源码文本。
        pos: 字符偏移。

    返回：
        偏移对应的 1-based 行号。
    """
    return text.count('\n', 0, pos) + 1


# 执行源码解析辅助逻辑。
def mask_source(text: str) -> tuple[str, list[JavadocBlock]]:
    """参数：
        text: Java 源码文本。

    返回：
        字符串与 Javadoc 列表；字符串/注释被空格掩码但保留换行。
    """
    chars = list(text)
    javadocs: list[JavadocBlock] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith('//', i):
            start = i
            i += 2
            while i < n and text[i] != '\n':
                i += 1
            _mask(chars, start, i)
            continue
        if text.startswith('/*', i):
            start = i
            i += 2
            while i < n and not text.startswith('*/', i):
                i += 1
            end = min(n, i + 2)
            if text.startswith('/**', start):
                javadocs.append(
                    JavadocBlock(start=start, end=end, line=_line(text, start), text=text[start:end])
                )
            _mask(chars, start, end)
            i = end
            continue
        if text.startswith('"""', i):
            start = i
            i += 3
            while i < n and not text.startswith('"""', i):
                i += 1
            _mask(chars, start, min(n, i + 3))
            i = min(n, i + 3)
            continue
        if text[i] in {'"', "'"}:
            quote = text[i]
            start = i
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            _mask(chars, start, i)
            continue
        i += 1
    return ''.join(chars), javadocs


# 执行源码解析辅助逻辑。
def _mask(chars: list[str], start: int, end: int) -> None:
    """参数：
        chars: 可变字符列表。
        start: 起始偏移。
        end: 结束偏移。
    """
    for index in range(start, min(end, len(chars))):
        if chars[index] != '\n':
            chars[index] = ' '


# 执行源码解析辅助逻辑。
def _skip_space(text: str, pos: int) -> int:
    """参数：
        text: 源码文本。
        pos: 起始偏移。

    返回：
        下一个非空白字符偏移。
    """
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


# 执行源码解析辅助逻辑。
def _find_matching(text: str, open_index: int, open_char: str, close_char: str) -> int:
    """参数：
        text: 已掩码源码文本。
        open_index: 左括号偏移。
        open_char: 左括号字符。
        close_char: 右括号字符。

    返回：
        匹配右括号偏移；找不到时返回 -1。
    """
    depth = 0
    for index in range(open_index, len(text)):
        ch = text[index]
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1


# 执行源码解析辅助逻辑。
def _skip_type_params(masked: str, pos: int) -> int:
    """参数：
        masked: 已掩码源码文本。
        pos: record 名称后的偏移。

    返回：
        跳过可选类型参数后的偏移。
    """
    pos = _skip_space(masked, pos)
    if pos < len(masked) and masked[pos] == '<':
        close = _find_matching(masked, pos, '<', '>')
        if close >= 0:
            return close + 1
    return pos


# 执行源码解析辅助逻辑。
def split_components(masked_components: str, base_offset: int, original: str) -> list[tuple[str, int]]:
    """参数：
        masked_components: record header 中 component 原文对应的掩码文本。
        base_offset: component 片段在原源码中的起始偏移。
        original: 完整源码文本。

    返回：
        component 片段和起始行号列表。
    """
    result: list[tuple[str, int]] = []
    start = 0
    angle = paren = bracket = brace = 0
    for index, ch in enumerate(masked_components):
        if ch == '<':
            angle += 1
        elif ch == '>' and angle:
            angle -= 1
        elif ch == '(':
            paren += 1
        elif ch == ')' and paren:
            paren -= 1
        elif ch == '[':
            bracket += 1
        elif ch == ']' and bracket:
            bracket -= 1
        elif ch == '{':
            brace += 1
        elif ch == '}' and brace:
            brace -= 1
        elif ch == ',' and not (angle or paren or bracket or brace):
            piece = masked_components[start:index].strip()
            if piece:
                result.append((piece, _line(original, base_offset + start)))
            start = index + 1
    piece = masked_components[start:].strip()
    if piece:
        result.append((piece, _line(original, base_offset + start)))
    return result


# 执行源码解析辅助逻辑。
def _component_name(component: str) -> str | None:
    """参数：
        component: 单个 record component 声明片段。

    返回：
        component 名称；无法解析时返回 None。
    """
    names = IDENT.findall(component)
    if not names:
        return None
    return names[-1]


# 执行源码解析辅助逻辑。
def extract_records(text: str) -> tuple[str, list[JavadocBlock], list[RecordDecl]]:
    """参数：
        text: Java 源码文本。

    返回：
        掩码文本、Javadoc 列表和 record 声明列表。
    """
    masked, javadocs = mask_source(text)
    records: list[RecordDecl] = []
    for match in re.finditer(r'\brecord\s+([A-Za-z_$][A-Za-z0-9_$]*)', masked):
        name = match.group(1)
        pos = _skip_type_params(masked, match.end())
        pos = _skip_space(masked, pos)
        if pos >= len(masked) or masked[pos] != '(':
            continue
        close = _find_matching(masked, pos, '(', ')')
        if close < 0:
            continue
        components: dict[str, int] = {}
        for component, line in split_components(masked[pos + 1 : close], pos + 1, text):
            component_name = _component_name(component)
            if component_name:
                components[component_name] = line
        records.append(
            RecordDecl(
                name=name,
                line=_line(text, match.start()),
                start=match.start(),
                components=components,
            )
        )
    return masked, javadocs, records


# 执行源码解析辅助逻辑。
def nearest_javadoc(
    masked: str,
    javadocs: list[JavadocBlock],
    record: RecordDecl,
) -> JavadocBlock | None:
    """参数：
        masked: 已掩码源码文本。
        javadocs: 文件内 Javadoc 块。
        record: record 声明。

    返回：
        record 类型 Javadoc；不存在时返回 None。
    """
    for block in reversed(javadocs):
        if block.end > record.start:
            continue
        between = masked[block.end : record.start].strip()
        if not between or _only_annotations_and_modifiers(masked[block.end : record.start]):
            return block
        return block
    return None


# 执行源码解析辅助逻辑。
def _only_annotations_and_modifiers(segment: str) -> bool:
    """参数：
        segment: Javadoc 与 record 关键字之间的源码片段。

    返回：
        片段只包含 record 修饰符和注解时返回 true。
    """
    pos = 0
    n = len(segment)
    while True:
        pos = _skip_space(segment, pos)
        if pos >= n:
            return True
        if segment[pos] == '@':
            pos += 1
            match = QUALIFIED_IDENT.match(segment, pos)
            if match is None:
                return False
            pos = match.end()
            pos = _skip_space(segment, pos)
            if pos < n and segment[pos] == '(':
                close = _find_matching(segment, pos, '(', ')')
                if close < 0:
                    return False
                pos = close + 1
            continue
        match = IDENT.match(segment, pos)
        if match is not None and match.group(0) in JAVA_MODIFIERS:
            pos = match.end()
            continue
        return False


# 执行源码解析辅助逻辑。
def parse_param_docs(javadoc: JavadocBlock) -> dict[str, str]:
    """参数：
        javadoc: Javadoc 注释块。

    返回：
        `@param` 名称到说明文本的映射。
    """
    body = javadoc.text
    if body.startswith('/**'):
        body = body[3:]
    if body.endswith('*/'):
        body = body[:-2]
    params: dict[str, list[str]] = {}
    current: str | None = None
    for raw in body.splitlines():
        line = re.sub(r'^\s*\*\s?', '', raw).strip()
        if not line:
            continue
        match = re.match(r'@param\s+([A-Za-z_$][A-Za-z0-9_$]*|<[^>]+>)\s*(.*)$', line)
        if match:
            current = match.group(1)
            params.setdefault(current, [])
            if match.group(2).strip():
                params[current].append(match.group(2).strip())
            continue
        if line.startswith('@'):
            current = None
            continue
        if current is not None:
            params[current].append(line)
    return {name: ' '.join(parts).strip() for name, parts in params.items()}


# 执行源码解析辅助逻辑。
def check_file(path: Path) -> list[Violation]:
    """参数：
        path: 待检查 Java 文件路径。

    返回：
        违规列表。
    """
    text = path.read_text(encoding='utf-8')
    masked, javadocs, records = extract_records(text)
    violations: list[Violation] = []
    for record in records:
        block = nearest_javadoc(masked, javadocs, record)
        if block is None:
            violations.append(
                Violation(
                    str(path),
                    record.line,
                    'RECORD_JAVADOC_MISSING',
                    f'record {record.name} 缺少类型 Javadoc，无法说明 components',
                )
            )
            continue
        params = parse_param_docs(block)
        for component, component_line in record.components.items():
            desc = params.get(component)
            if desc is None:
                violations.append(
                    Violation(
                        str(path),
                        component_line,
                        'RECORD_COMPONENT_PARAM_MISSING',
                        f'record {record.name} component {component} 缺少 @param 说明',
                    )
                )
            elif not HAN.search(desc):
                violations.append(
                    Violation(
                        str(path),
                        component_line,
                        'RECORD_COMPONENT_PARAM_NOT_CHINESE',
                        f'record {record.name} component {component} 的 @param 说明必须包含中文',
                    )
                )
    return violations


# 执行源码解析辅助逻辑。
def discover(values: list[str]) -> list[Path]:
    """参数：
        values: 命令行传入的路径列表。

    返回：
        待扫描 Java 文件列表。
    """
    result: set[Path] = set()
    for raw in values:
        path = Path(raw)
        if path.is_file() and path.suffix == '.java':
            result.add(path)
        elif path.is_dir():
            result.update(
                p
                for p in path.rglob('*.java')
                if not (set(p.parts) & EXCLUDED_PARTS) and _is_main_java_source(p)
            )
    return sorted(result, key=lambda item: item.as_posix())


# 执行源码解析辅助逻辑。
def _is_main_java_source(path: Path) -> bool:
    """参数：
        path: 待判断 Java 文件路径。

    返回：
        文件位于 Gradle/Maven `src/main/java` 源集时返回 true。
    """
    parts = path.parts
    return any(
        parts[index : index + 3] == ('src', 'main', 'java')
        for index in range(0, max(0, len(parts) - 2))
    )


# 执行源码解析辅助逻辑。
def _load_files_from(path: Path) -> list[str]:
    """参数：
        path: 文件列表路径。

    返回：
        路径字符串列表。
    """
    raw = path.read_text(encoding='utf-8').strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, str)]
    return []


# 执行源码解析辅助逻辑。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='检查 Java record component 中文 Javadoc')
    parser.add_argument('paths', nargs='*', default=['java'])
    parser.add_argument('--files-from', help='从 JSON 或换行文本读取待检查路径')
    args = parser.parse_args()

    paths = _load_files_from(Path(args.files_from)) if args.files_from else args.paths
    violations: list[Violation] = []
    for path in discover(paths):
        violations.extend(check_file(path))

    for violation in violations:
        print(
            f'{violation.path}:{violation.line}: {violation.code}: {violation.message}',
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == '__main__':
    raise SystemExit(main())
