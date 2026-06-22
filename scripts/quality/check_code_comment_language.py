#!/usr/bin/env python3
"""词法级中文注释检查器：近似验证 Java/Kotlin 注释以中文为主体。

设计原则：
- 词法状态机提取注释，跳过 string/text block/char literal。
- 中文字符计数为主体比例判断。
- 技术术语允许英文（内置术语表 + 可选 policy 文件扩展）。
- 占位/低信息注释（TODO、待补充等）失败。
- 支持 JSON report 和有界多线程。
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# ============================================================
# 正则与内置术语表
# ============================================================
HAN = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
LATIN = re.compile(r'[A-Za-z]')
PLACEHOLDER = re.compile(
    r'\b(?:TODO|TBD|FIXME|XXX)\b|待补充|以后补|稍后处理|临时注释', re.I
)
DIRECTIVE = re.compile(
    r'^(?:SPDX-|Copyright|noinspection|language=|region|endregion|'
    r'spotless:|formatter:|CHECKSTYLE|PMD|ktlint|generated)',
    re.I,
)
URL = re.compile(r'https?://\S+')
HTML = re.compile(r'</?[A-Za-z][^>]*>')
TAG = re.compile(
    r'\{@(?:code|link|linkplain|literal|value)\s+[^}]*}'
    r'|@(?:param|return|throws|exception|since|see|deprecated)\b'
)
IDENT = re.compile(
    r'`[^`]+`|\b(?:[A-Za-z_$][\w$]*\.)+[A-Za-z_$][\w$]*\b'
)

TERMS: set[str] = {
    'Java', 'JVM', 'Gradle', 'Kotlin', 'DSL', 'JUnit', 'Javadoc', 'DocLint',
    'JSON', 'JSONL', 'NDJSON', 'SQLite', 'Jackson', 'Picocli', 'API', 'CLI',
    'record', 'enum', 'sealed', 'interface', 'token', 'tool', 'agent',
    'session', 'SHA', 'UTF', 'stdout', 'stderr', 'fixture', 'artifact',
    'schema', 'hash', 'ID', 'UUID', 'HTTP', 'SQL', 'Git', 'Python',
}

# 排除的目录片段
EXCLUDED_PARTS = {
    'build', '.gradle', 'generated', 'gen', 'third_party', 'vendor',
    'node_modules',
}


# ============================================================
# 数据结构
# ============================================================
@dataclass(frozen=True)
class Comment:
    """一条从源码中提取的注释。"""
    path: str
    line: int
    kind: str
    text: str


@dataclass(frozen=True)
class Violation:
    """一条注释违规。"""
    path: str
    line: int
    code: str
    message: str
    preview: str


# ============================================================
# 注释提取 — 词法状态机
# ============================================================
def extract(path: Path) -> list[Comment]:
    """从源文件中提取所有注释，跳过字符串和字符字面量。"""
    text = path.read_text(encoding='utf-8')
    out: list[Comment] = []
    i = 0
    n = len(text)
    state = 'normal'
    start = 0
    depth = 0

    def line(pos: int) -> int:
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
                out.append(Comment(str(path), line(start), 'line', text[start + 2:i]))
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
                    out.append(Comment(str(path), line(start), kind, text[start + 2:i - 2]))
                    state = 'normal'
            else:
                i += 1

    if state == 'line':
        out.append(Comment(str(path), line(start), 'line', text[start + 2:]))
    return out


# ============================================================
# 规范化与检查
# ============================================================
def normalize(text: str, terms: set[str]) -> str:
    """去除注释格式、URL、HTML 标签、Javadoc 标记和已知术语。"""
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
            ' ', value, flags=re.I,
        )
    return re.sub(r'\s+', ' ', value).strip()


def check(
    comment: Comment, terms: set[str], forbidden: tuple[str, ...]
) -> list[Violation]:
    """检查单条注释是否合规。"""
    raw = comment.text.strip()
    first = re.sub(r'^\s*\*?\s?', '', raw.splitlines()[0]).strip() if raw else ''
    if not raw or DIRECTIVE.match(first):
        return []

    # 检查禁止的非规范翻译
    for word in forbidden:
        if word in raw:
            return [Violation(
                comment.path, comment.line, 'TECH_TERM_NOT_CANONICAL',
                f'技术术语应使用约定英文，禁止：{word}', first[:160],
            )]

    # 检查占位/低信息注释
    if PLACEHOLDER.search(raw):
        return [Violation(
            comment.path, comment.line, 'COMMENT_LOW_INFORMATION',
            '注释包含占位或低信息表达', first[:160],
        )]

    value = normalize(raw, terms)
    if not value or not (HAN.search(value) or LATIN.search(value)):
        return []

    han_count = len(HAN.findall(value))
    latin_count = len(LATIN.findall(value))
    min_han = 4 if comment.kind != 'line' else 2
    min_ratio = 0.12 if comment.kind != 'line' else 0.08
    ratio = han_count / max(1, han_count + latin_count)

    violations: list[Violation] = []
    if han_count < min_han or ratio < min_ratio:
        violations.append(Violation(
            comment.path, comment.line, 'COMMENT_NOT_CHINESE_DOMINANT',
            f'Han={han_count}, Latin={latin_count}, ratio={ratio:.3f}',
            first[:160],
        ))
    if '{@inheritDoc}' in raw and han_count < 4:
        violations.append(Violation(
            comment.path, comment.line, 'INHERITDOC_WITHOUT_CHINESE',
            '不能只使用 inheritDoc 代替中文说明', first[:160],
        ))
    return violations


# ============================================================
# 文件发现
# ============================================================
def discover(values: list[str]) -> list[Path]:
    """从给定路径发现所有 Java/Kotlin 源文件。"""
    result: set[Path] = set()
    for raw in values:
        p = Path(raw)
        if p.is_file() and p.suffix in {'.java', '.kt', '.kts'}:
            result.add(p)
        elif p.is_dir():
            for ext in ('*.java', '*.kt', '*.kts'):
                result.update(
                    x for x in p.rglob(ext)
                    if not (set(x.parts) & EXCLUDED_PARTS)
                )
    return sorted(result, key=lambda x: x.as_posix())


# ============================================================
# 主入口
# ============================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description='词法级中文注释检查器',
    )
    ap.add_argument(
        'paths', nargs='*',
        default=['java', 'build-logic', 'build.gradle.kts', 'settings.gradle.kts'],
    )
    ap.add_argument('--jobs', default='auto')
    ap.add_argument('--policy', help='JSON 术语策略文件路径')
    ap.add_argument('--json-report', help='JSON 报告输出路径')
    ap.add_argument('--cache', help='增量缓存路径')
    ap.add_argument('--files-from', help='从 JSON 文件读取要扫描的路径列表')
    a = ap.parse_args()

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

    files = discover(paths)
    jobs = (
        min(16, max(1, os.cpu_count() or 1), max(1, len(files)))
        if a.jobs == 'auto'
        else max(1, int(a.jobs))
    )

    # 增量缓存
    policy_hash = hashlib.sha256(
        json.dumps(sorted(terms)).encode() + json.dumps(sorted(forbidden)).encode()
        + b'checker-v1'
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

    def scan(path: Path) -> tuple[str, str, list[Violation]]:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = path.as_posix()
        old = cache.get('entries', {}).get(key)
        if old and old.get('sha256') == digest:
            return str(path), digest, [
                Violation(**x) for x in old.get('violations', [])
            ]
        violations: list[Violation] = []
        for c in extract(path):
            violations.extend(check(c, terms, forbidden))
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
                ensure_ascii=False, sort_keys=True, indent=2,
            ) + '\n',
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
                ensure_ascii=False, indent=2,
            ) + '\n',
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
