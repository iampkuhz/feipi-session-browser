#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TYPE_KEYWORDS = {"class", "interface", "enum", "record"}
MODIFIERS = {
    "public",
    "protected",
    "private",
    "static",
    "final",
    "abstract",
    "default",
    "sealed",
    "non-sealed",
    "strictfp",
    "native",
    "synchronized",
    "transient",
    "volatile",
}


@dataclass(frozen=True)
class JavaType:
    package: str
    simple_name: str
    qualified_name: str
    kind: str
    header: str
    body: str
    parent: str | None = None


def strip_comments_and_literals(text: str) -> str:
    result: list[str] = []
    i = 0
    state = "code"
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                result.extend("  ")
                i += 2
                state = "line_comment"
            elif ch == "/" and nxt == "*":
                result.extend("  ")
                i += 2
                state = "block_comment"
            elif ch == '"' and text[i : i + 3] == '"""':
                result.extend('"""')
                i += 3
                state = "text_block"
            elif ch == '"':
                result.append('"')
                i += 1
                state = "string"
            elif ch == "'":
                result.append("'")
                i += 1
                state = "char"
            else:
                result.append(ch)
                i += 1
        elif state == "line_comment":
            if ch == "\n":
                result.append("\n")
                state = "code"
            else:
                result.append(" ")
            i += 1
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                result.extend("  ")
                i += 2
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
        elif state == "string":
            if ch == "\\":
                result.extend("  ")
                i += 2
            elif ch == '"':
                result.append('"')
                i += 1
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
        elif state == "char":
            if ch == "\\":
                result.extend("  ")
                i += 2
            elif ch == "'":
                result.append("'")
                i += 1
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
        elif state == "text_block":
            if text[i : i + 3] == '"""':
                result.extend('"""')
                i += 3
                state = "code"
            else:
                result.append("\n" if ch == "\n" else " ")
                i += 1
    return "".join(result)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def remove_annotations(value: str) -> str:
    previous = None
    current = value
    while previous != current:
        previous = current
        current = re.sub(r"@\w+(?:\.\w+)*(?:\s*\([^()]*\))?\s*", "", current)
    return current


def find_matching(text: str, start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == open_ch:
            depth += 1
        elif text[index] == close_ch:
            depth -= 1
            if depth == 0:
                return index
    return -1


def split_top_level(value: str, separator: str = ",") -> list[str]:
    parts: list[str] = []
    start = 0
    angle = paren = bracket = brace = 0
    for index, ch in enumerate(value):
        if ch == "<":
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch == "(":
            paren += 1
        elif ch == ")" and paren:
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]" and bracket:
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}" and brace:
            brace -= 1
        elif ch == separator and not (angle or paren or bracket or brace):
            parts.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def package_name(text: str) -> str:
    match = re.search(r"\bpackage\s+([\w.]+)\s*;", text)
    return match.group(1) if match else ""


def locate_type_declarations(text: str) -> list[tuple[int, int, str, str]]:
    declarations: list[tuple[int, int, str, str]] = []
    pattern = re.compile(r"\b(class|interface|enum|record)\s+([A-Za-z_]\w*)")
    for match in pattern.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        prefix_start = max(text.rfind(";", 0, match.start()) + 1, text.rfind("}", 0, match.start()) + 1, line_start)
        prefix = text[prefix_start : match.start()]
        if "@interface" in text[max(0, match.start() - 2) : match.start() + len("interface")]:
            kind = "@interface"
        else:
            kind = match.group(1)
        brace = text.find("{", match.end())
        if brace == -1:
            continue
        header = normalize_space(text[prefix_start:brace])
        declarations.append((prefix_start, brace, kind, match.group(2)))
    return declarations


def extract_types(text: str, package: str) -> list[JavaType]:
    types: list[JavaType] = []

    def visit(region: str, owner: str | None = None, qprefix: str | None = None) -> None:
        for start, brace, kind, simple_name in locate_type_declarations(region):
            header = normalize_space(region[start:brace])
            if not is_public_or_protected_type(header, owner is not None):
                continue
            end = find_matching(region, brace, "{", "}")
            if end == -1:
                continue
            body = region[brace + 1 : end]
            qualified = f"{package}.{simple_name}" if not qprefix else f"{qprefix}.{simple_name}"
            types.append(JavaType(package, simple_name, qualified, kind, header, body, owner))
            visit(body, qualified, qualified)

    visit(text)
    return types


def is_public_or_protected_type(header: str, nested: bool) -> bool:
    clean = normalize_space(remove_annotations(header))
    tokens = clean.split()
    if "public" in tokens or "protected" in tokens:
        return True
    return nested and "private" not in tokens


def declaration_until_body_members(body: str) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    start = 0
    depth = 0
    paren = angle = bracket = 0
    index = 0
    while index < len(body):
        ch = body[index]
        if ch == "<":
            angle += 1
        elif ch == ">" and angle:
            angle -= 1
        elif ch == "(":
            paren += 1
        elif ch == ")" and paren:
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]" and bracket:
            bracket -= 1
        elif ch == "{":
            if depth == 0 and paren == 0 and bracket == 0:
                decl = body[start:index].strip()
                if decl:
                    members.append((decl, "block"))
                end = find_matching(body, index, "{", "}")
                if end == -1:
                    break
                index = end
                start = index + 1
            else:
                depth += 1
        elif ch == "}" and depth:
            depth -= 1
        elif ch == ";" and depth == 0 and paren == 0 and angle == 0 and bracket == 0:
            decl = body[start:index].strip()
            if decl:
                members.append((decl, "semicolon"))
            start = index + 1
        index += 1
    return members


def type_visibility(header: str) -> str:
    clean = normalize_space(remove_annotations(header))
    tokens = clean.split()
    if "protected" in tokens:
        return "protected"
    return "public"


def canonical_type_header(java_type: JavaType) -> str:
    clean = normalize_space(remove_annotations(java_type.header))
    clean = re.sub(r"\b(public|protected|private)\b\s*", "", clean)
    return normalize_space(clean)


def canonical_param(param: str) -> str:
    clean = normalize_space(remove_annotations(param))
    clean = re.sub(r"\b(final)\b\s*", "", clean)
    clean = re.sub(r"\s*=.*$", "", clean).strip()
    return clean


def record_components(java_type: JavaType) -> list[str]:
    if java_type.kind != "record":
        return []
    match = re.search(r"\brecord\s+" + re.escape(java_type.simple_name) + r"\s*\(", java_type.header)
    if not match:
        return []
    open_index = java_type.header.find("(", match.end() - 1)
    close_index = find_matching(java_type.header, open_index, "(", ")")
    if close_index == -1:
        return []
    result = []
    for param in split_top_level(java_type.header[open_index + 1 : close_index]):
        clean = canonical_param(param)
        if not clean:
            continue
        name = clean.split()[-1].replace("...", "")
        typ = clean[: -len(name)].strip()
        result.append(f"component {java_type.qualified_name} {name}: {typ}")
    return result


def enum_constants(java_type: JavaType) -> list[str]:
    if java_type.kind != "enum":
        return []
    declarations = declaration_until_body_members(java_type.body)
    if not declarations:
        return []
    first, terminator = declarations[0]
    if terminator != "semicolon" or re.search(r"\b(public|protected|private|static|final|void|class|interface|enum|record)\b", first):
        return []
    constants = []
    for item in split_top_level(first):
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)\b", item)
        if match:
            constants.append(f"enum-constant {java_type.qualified_name} {match.group(1)}")
    return constants


def member_lines(java_type: JavaType) -> list[str]:
    lines: list[str] = []
    implicit_public = java_type.kind in {"interface", "@interface"}
    for raw, terminator in declaration_until_body_members(java_type.body):
        raw_clean = normalize_space(remove_annotations(raw))
        if not raw_clean:
            continue
        if re.search(r"\b(class|interface|enum|record)\s+[A-Za-z_]\w*", raw_clean):
            continue
        if java_type.kind == "enum" and terminator == "semicolon" and raw == declaration_until_body_members(java_type.body)[0][0]:
            continue
        tokens = raw_clean.split()
        visible = "public" in tokens or "protected" in tokens or implicit_public
        if not visible:
            continue
        visibility = "protected" if "protected" in tokens else "public"
        canonical = re.sub(r"\b(public|protected|private)\b\s*", "", raw_clean)
        canonical = normalize_space(canonical)
        if "(" in canonical and ")" in canonical:
            before_paren = canonical[: canonical.find("(")].strip()
            name = before_paren.split()[-1] if before_paren else ""
            if name == java_type.simple_name:
                kind = "constructor"
            else:
                kind = "method"
            lines.append(f"{kind} {java_type.qualified_name} {visibility} {canonical}")
        elif terminator == "block" and canonical == java_type.simple_name:
            lines.append(f"constructor {java_type.qualified_name} {visibility} {java_type.simple_name}()")
        else:
            names_part = canonical
            if "=" in names_part:
                names_part = names_part.split("=", 1)[0].strip()
            pieces = names_part.split()
            if len(pieces) >= 2:
                field_name = pieces[-1].replace("[]", "")
                field_type = " ".join(pieces[:-1])
                lines.append(f"field {java_type.qualified_name} {visibility} {field_name}: {field_type}")
    return lines


def snapshot_for_file(path: Path, root: Path) -> list[str]:
    text = strip_comments_and_literals(path.read_text(encoding="utf-8"))
    package = package_name(text)
    lines: list[str] = []
    for java_type in extract_types(text, package):
        module = module_name(path, root)
        visibility = type_visibility(java_type.header)
        lines.append(
            f"type {java_type.qualified_name} {visibility} {java_type.kind} "
            f"[{module}] {canonical_type_header(java_type)}"
        )
        lines.extend(record_components(java_type))
        lines.extend(enum_constants(java_type))
        lines.extend(member_lines(java_type))
    return lines


def module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) >= 1:
        return parts[0]
    return "."


def generate_snapshot(java_root: Path) -> str:
    files = sorted(java_root.glob("**/src/main/java/**/*.java"), key=lambda p: p.as_posix())
    lines: list[str] = []
    for path in files:
        if "/build/" in path.as_posix():
            continue
        lines.extend(snapshot_for_file(path, java_root))
    unique = sorted(set(lines))
    header = [
        "# Java public API snapshot",
        "# Generated by scripts/quality/check_java_api_snapshot.py --write",
        "# Update only after approving intentional public API changes.",
        "",
    ]
    return "\n".join(header + unique) + "\n"


def check_snapshot(snapshot_path: Path, current: str) -> int:
    if not snapshot_path.exists():
        print(f"API snapshot baseline is missing: {snapshot_path}", file=sys.stderr)
        return 1
    expected = snapshot_path.read_text(encoding="utf-8")
    if expected == current:
        print(f"Java API snapshot matches {snapshot_path}")
        return 0
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        current.splitlines(keepends=True),
        fromfile=str(snapshot_path),
        tofile="current-java-public-api",
    )
    sys.stderr.writelines(diff)
    return 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check deterministic Java public API snapshot.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="compare current API to the approved baseline")
    mode.add_argument("--write", action="store_true", help="write the current API as the approved baseline")
    parser.add_argument("--java-root", type=Path, default=Path("java"))
    parser.add_argument("--snapshot", type=Path, default=Path("config/api-snapshots/java-public-api.txt"))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    current = generate_snapshot(args.java_root)
    if args.write:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_text(current, encoding="utf-8")
        print(f"Wrote Java API snapshot to {args.snapshot}")
        return 0
    return check_snapshot(args.snapshot, current)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
