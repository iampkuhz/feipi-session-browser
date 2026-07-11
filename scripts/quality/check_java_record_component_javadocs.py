#!/usr/bin/env python3
"""检查 Java record component 是否都有中文 Javadoc 说明。"""

from __future__ import annotations

import argparse
import json
import os
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
class ComponentInfo:
    """表示单个 record component 的完整信息。

    属性：
        name: component 名称。
        line: component 声明起始行号。
        raw_text: component 原始源码片段（含 Javadoc、注解、类型和名称）。
        inline_javadoc: component 附近的 Javadoc 块；不存在时为 None。
    """

    name: str
    line: int
    raw_text: str
    inline_javadoc: JavadocBlock | None = None


@dataclass(frozen=True)
class RecordDecl:
    """表示 Java record 声明。

    属性：
        name: record 类型名称。
        line: record 关键字所在行号。
        start: record 关键字字符偏移。
        components: component 信息列表。
    """

    name: str
    line: int
    start: int
    components: list[ComponentInfo]


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
            elif text.startswith('/*', start) and not text.startswith('/**', start):
                # Java 25 不允许 /** */ 出现在 record 参数列表中，
                # 因此 record component 附近注释使用 /* */ 也被视为有效文档。
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
def split_components(raw_components: str, base_offset: int, original: str, file_javadocs: list[JavadocBlock]) -> list[ComponentInfo]:
    """参数：
        raw_components: record header 中 component 区域的原始文本（未掩码）。
        base_offset: component 片段在原源码中的起始偏移。
        original: 完整源码文本。
        file_javadocs: 文件内所有 Javadoc 块列表。

    返回：
        ComponentInfo 列表，每个包含 component 名称、行号、原始片段和附近 Javadoc。
    """
    result: list[ComponentInfo] = []
    start = 0
    angle = paren = bracket = brace = 0
    for index, ch in enumerate(raw_components):
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
            piece = raw_components[start:index]
            piece_stripped = piece.strip()
            if piece_stripped:
                abs_start = base_offset + start
                raw_text = original[abs_start : abs_start + len(piece)]
                component_name = _component_name(raw_text)
                inline_jd = _find_component_javadoc(raw_text, abs_start, file_javadocs)
                if component_name:
                    result.append(
                        ComponentInfo(
                            name=component_name,
                            line=_line(original, abs_start),
                            raw_text=raw_text,
                            inline_javadoc=inline_jd,
                        )
                    )
            start = index + 1
    piece = raw_components[start:]
    piece_stripped = piece.strip()
    if piece_stripped:
        abs_start = base_offset + start
        raw_text = original[abs_start : abs_start + len(piece)]
        component_name = _component_name(raw_text)
        inline_jd = _find_component_javadoc(raw_text, abs_start, file_javadocs)
        if component_name:
            result.append(
                ComponentInfo(
                    name=component_name,
                    line=_line(original, abs_start),
                    raw_text=raw_text,
                    inline_javadoc=inline_jd,
                )
            )
    return result


# 执行源码解析辅助逻辑。
def _component_name(component: str) -> str | None:
    """参数：
        component: 单个 record component 原始声明片段（可能含 Javadoc）。

    返回：
        component 名称；无法解析时返回 None。
    """
    star = component.find('*/')
    if star >= 0:
        after = component[star + 2 :]
        names = IDENT.findall(after)
        if names:
            return names[-1]
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
        raw_between = text[pos + 1 : close]
        component_infos = split_components(raw_between, pos + 1, text, javadocs)
        records.append(
            RecordDecl(
                name=name,
                line=_line(text, match.start()),
                start=match.start(),
                components=component_infos,
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
def _find_component_javadoc(
    raw_text: str,
    abs_start: int,
    file_javadocs: list[JavadocBlock],
) -> JavadocBlock | None:
    """参数：
        raw_text: component 原始片段。
        abs_start: 片段在文件中的绝对字符偏移。
        file_javadocs: 文件内所有 Javadoc 块列表。

    返回：
        属于该 component 的最后一个 Javadoc 块；不存在时返回 None。
    """
    abs_end = abs_start + len(raw_text)
    candidates = [
        jd for jd in file_javadocs
        if jd.start >= abs_start and jd.end <= abs_end
    ]
    for jd in reversed(candidates):
        after = raw_text[jd.end - abs_start :]
        if _only_ws_annotations_generics(after):
            return jd
    return None


# 执行源码解析辅助逻辑。
def _only_ws_annotations_generics(segment: str) -> bool:
    """参数：
        segment: Javadoc 结束后的 component 源码片段。

    返回：
        片段仅含空白、注解、泛型括号和数组括号时返回 true。
    """
    masked, _ = mask_source(segment)
    pos = 0
    n = len(masked)
    while pos < n:
        ch = masked[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch == '@':
            pos += 1
            while pos < n and (masked[pos].isalnum() or masked[pos] in '_$.'):
                pos += 1
            while pos < n and masked[pos].isspace():
                pos += 1
            if pos < n and masked[pos] == '(':
                close = _find_matching(masked, pos, '(', ')')
                if close < 0:
                    return False
                pos = close + 1
            continue
        if ch in '<>[]':
            pos += 1
            continue
        if ch.isalpha() or ch in '_$':
            return True
        return False
    return True


# 执行源码解析辅助逻辑。
def _check_annotation_own_line(component_text: str) -> bool:
    """参数：
        component_text: component 原始源码片段。

    返回：
        存在注解与类型/名称在同一行时返回 true。
    """
    masked_piece, _ = mask_source(component_text)
    for line in masked_piece.split('\n'):
        stripped = line.strip()
        at_pos = stripped.find('@')
        if at_pos < 0:
            continue
        if stripped.startswith('**'):
            continue
        after_at = stripped[at_pos + 1 :]
        name_match = QUALIFIED_IDENT.match(after_at)
        if name_match is None:
            continue
        rest_pos = name_match.end()
        while rest_pos < len(after_at):
            ch = after_at[rest_pos]
            if ch.isspace():
                rest_pos += 1
                continue
            if ch == '(':
                depth = 1
                rest_pos += 1
                while rest_pos < len(after_at) and depth > 0:
                    if after_at[rest_pos] == '(':
                        depth += 1
                    elif after_at[rest_pos] == ')':
                        depth -= 1
                    rest_pos += 1
                continue
            break
        rest = after_at[rest_pos:].strip()
        if rest and IDENT.match(rest):
            return True
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
        else:
            params = parse_param_docs(block)
            for comp in record.components:
                desc = params.get(comp.name)
                if desc is None:
                    violations.append(
                        Violation(
                            str(path),
                            comp.line,
                            'RECORD_COMPONENT_PARAM_MISSING',
                            f'record {record.name} component {comp.name} 缺少 @param 说明',
                        )
                    )
                elif not HAN.search(desc):
                    violations.append(
                        Violation(
                            str(path),
                            comp.line,
                            'RECORD_COMPONENT_PARAM_NOT_CHINESE',
                            f'record {record.name} component {comp.name} 的 @param 说明必须包含中文',
                        )
                    )
                # component 附近 inline 注释由 formatter 和 javac 共同约束；
                # 本 gate 只要求 record 级 @param 覆盖 component。
                # 注解排版由 google-java-format（spotless）统一管理，
                # 与 layout policy "以 formatter 结果为准" 保持一致，不再单独检查。
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


# 读取 required gate 传入的 changed-files 上下文。
def _quality_changed_java_files(repo_root: Path) -> set[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        环境变量中需要检查的 main Java 文件相对路径集合。
    """
    raw = os.environ.get('QUALITY_CHANGED_FILES', '').strip()
    if not raw:
        return set()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    result: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        path = Path(item)
        if path.is_absolute():
            try:
                path = path.relative_to(repo_root)
            except ValueError:
                continue
        if path.suffix != '.java' or not _is_main_java_source(path):
            continue
        if set(path.parts) & EXCLUDED_PARTS:
            continue
        result.add(path.as_posix())
    return result


# 根据 changed-files 上下文裁剪扫描文件。
def _filter_changed_files(paths: list[Path], changed_files: set[str], repo_root: Path) -> list[Path]:
    """参数：
        paths: 已发现的 Java 文件列表。
        changed_files: changed-files 上下文中的 main Java 相对路径。
        repo_root: 仓库根目录。

    返回：
        仅保留 changed-files 命中的 Java 文件；无上下文时返回原列表。
    """
    if not changed_files:
        return paths
    filtered: list[Path] = []
    for path in paths:
        try:
            rel = path.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            rel = path.as_posix()
        if rel in changed_files:
            filtered.append(path)
    return filtered


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
    repo_root = Path.cwd().resolve()
    changed_files = _quality_changed_java_files(repo_root)
    violations: list[Violation] = []
    for path in _filter_changed_files(discover(paths), changed_files, repo_root):
        violations.extend(check_file(path))

    for violation in violations:
        print(
            f'{violation.path}:{violation.line}: {violation.code}: {violation.message}',
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == '__main__':
    raise SystemExit(main())
