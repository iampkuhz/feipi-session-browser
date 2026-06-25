#!/usr/bin/env python3
"""Validate context routes structure and required fields.

Only uses Python stdlib - implements minimal YAML parsing for routes structure.
"""

import sys
from pathlib import Path


REQUIRED_ROUTE_FIELDS = {'id', 'match', 'load'}

FORBIDDEN_FULL_LOAD_PATTERNS = {
    'docs/**',
    'skills/**',
    'harness/**',
    'historical_reports/**',
    'real_session_data/**',
}


def parse_inline_flow(value: str):
    """Parse inline flow mapping like {key: value} or flow list like [a, b]."""
    value = value.strip()
    if value.startswith('{') and value.endswith('}'):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        result = {}
        for pair in inner.split(','):
            if ':' in pair:
                k, _, v = pair.partition(':')
                result[k.strip()] = v.strip()
        return result
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip() for item in inner.split(',') if item.strip()]
    return None


def parse_simple_yaml(content: str) -> dict:
    """Parse the context routes YAML structure.

    Handles: top-level scalars, lists of mappings, nested mappings within
    list items, nested key+block values, inline flow collections.
    """
    lines = content.split('\n')
    result = {}
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        lstripped = line.lstrip()

        if not stripped or lstripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value and not value.startswith('['):
                result[key] = _parse_scalar(value)
                i += 1
            elif value.startswith('['):
                result[key] = parse_inline_flow(value) or value
                i += 1
            else:
                sub_lines = []
                j = i + 1
                while j < len(lines):
                    sl = lines[j]
                    ss = sl.rstrip()
                    sls = sl.lstrip()
                    if not ss or sls.startswith('#'):
                        j += 1
                        continue
                    si = len(sl) - len(sl.lstrip())
                    if si == 0:
                        break
                    sub_lines.append(sl)
                    j += 1

                if sub_lines:
                    sub_indent = len(sub_lines[0]) - len(sub_lines[0].lstrip())
                    sub_stripped = sub_lines[0].lstrip()
                    if sub_stripped.startswith('- '):
                        result[key] = _parse_list_of_mappings(sub_lines, sub_indent)
                    else:
                        result[key] = _parse_mapping(sub_lines, sub_indent)
                else:
                    result[key] = {}
                i = j
        else:
            i += 1

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_scalar(value: str):
    """Parse a scalar YAML value."""
    if value == '[]':
        return []
    if value == '{}':
        return {}
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_list_of_mappings(lines, base_indent):
    """Parse a YAML list whose items are mappings (``- key: value`` ...).

    Strategy: direct keys live at ``base_indent + 2``.  Everything deeper is
    block content for the most recent key.  Block content is parsed via
    ``_parse_block_value`` which auto-detects list vs mapping.
    """
    direct_key_indent = base_indent + 2
    items = []
    current_item = None
    current_key = None
    block_lines = []

    def _flush_block():
        nonlocal current_key, block_lines
        if current_key is not None and current_item is not None:
            if block_lines:
                bi = None
                for bl in block_lines:
                    bs = bl.rstrip()
                    bls = bl.lstrip()
                    if bs and not bls.startswith('#'):
                        bi = len(bl) - len(bl.lstrip())
                        break
                if bi is not None:
                    current_item[current_key] = _parse_block_value(
                        block_lines, bi
                    )
                else:
                    current_item[current_key] = {}
            else:
                current_item[current_key] = {}
        current_key = None
        block_lines = []

    for line in lines:
        stripped = line.rstrip()
        lstripped = line.lstrip()
        if not stripped or lstripped.startswith('#'):
            if current_key is not None:
                block_lines.append(line)
            continue

        indent = len(line) - len(line.lstrip())

        if indent < base_indent:
            break

        # ── New list item: ``- key: value`` ──────────────────────────────
        if lstripped.startswith('- ') and indent == base_indent:
            _flush_block()
            if current_item is not None:
                items.append(current_item)
            current_item = {}

            content = lstripped[2:]
            if ':' in content:
                k, _, v = content.partition(':')
                k = k.strip()
                v = v.strip()
                if v:
                    flow = parse_inline_flow(v)
                    current_item[k] = (
                        flow if flow is not None else _parse_scalar(v)
                    )
                else:
                    current_key = k
            continue

        if current_item is None:
            continue

        # ── Direct key at item-child indent ──────────────────────────────
        if indent == direct_key_indent and ':' in lstripped:
            _flush_block()
            k, _, v = lstripped.partition(':')
            k = k.strip()
            v = v.strip()
            if v:
                flow = parse_inline_flow(v)
                current_item[k] = (
                    flow if flow is not None else _parse_scalar(v)
                )
            else:
                current_key = k
            continue

        # ── Deeper than direct-key indent → block content ────────────────
        if current_key is not None and indent > direct_key_indent:
            block_lines.append(line)
            continue

    _flush_block()
    if current_item is not None:
        items.append(current_item)

    return items


def _parse_block_value(lines, base_indent):
    """Parse the block value under a key.

    Returns a list (if the block starts with ``- ``) or a dict (if the block
    starts with a mapping key).
    """
    first_content = None
    for line in lines:
        s = line.rstrip()
        ls = line.lstrip()
        if s and not ls.startswith('#'):
            first_content = ls
            break
    if first_content is None:
        return {}
    if first_content.startswith('- '):
        return _parse_block_list(lines, base_indent)
    return _parse_block_mapping(lines, base_indent)


def _parse_block_list(lines, base_indent):
    """Parse a block list (``- value`` items)."""
    result = []
    for line in lines:
        s = line.rstrip()
        ls = line.lstrip()
        if not s or ls.startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        if indent < base_indent:
            break
        if ls.startswith('- ') and indent == base_indent:
            val = ls[2:].strip()
            if ':' in val and _looks_like_key(val.partition(':')[0]):
                k, _, v = val.partition(':')
                k = k.strip()
                v = v.strip()
                result.append({k: _parse_scalar(v)} if v else {k: {}})
            else:
                result.append(_parse_scalar(val))
    return result


def _parse_block_mapping(lines, base_indent):
    """Parse a block mapping (``key: value`` pairs with possible sub-blocks)."""
    result = {}
    current_key = None
    sub_lines = []

    def _flush():
        nonlocal current_key, sub_lines
        if current_key is not None:
            if sub_lines:
                bi = None
                for bl in sub_lines:
                    bs = bl.rstrip()
                    bls = bl.lstrip()
                    if bs and not bls.startswith('#'):
                        bi = len(bl) - len(bl.lstrip())
                        break
                effective = bi or base_indent + 2
                result[current_key] = _parse_block_value(sub_lines, effective)
            else:
                result[current_key] = {}
        current_key = None
        sub_lines = []

    for line in lines:
        s = line.rstrip()
        ls = line.lstrip()
        if not s or ls.startswith('#'):
            if current_key is not None:
                sub_lines.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent < base_indent:
            break
        if indent == base_indent and ':' in ls:
            _flush()
            k, _, v = ls.partition(':')
            k = k.strip()
            v = v.strip()
            if v:
                flow = parse_inline_flow(v)
                result[k] = flow if flow is not None else _parse_scalar(v)
            else:
                current_key = k
            continue
        if current_key is not None and indent > base_indent:
            sub_lines.append(line)

    _flush()
    return result


def _parse_mapping(lines, base_indent):
    """Parse a YAML mapping block."""
    result = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        lstripped = line.lstrip()
        if not stripped or lstripped.startswith('#'):
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        if indent < base_indent:
            break
        if indent == base_indent and ':' in lstripped:
            k, _, v = lstripped.partition(':')
            k = k.strip()
            v = v.strip()
            if v:
                flow = parse_inline_flow(v)
                result[k] = flow if flow is not None else _parse_scalar(v)
            else:
                result[k] = {}
        i += 1
    return result


def _looks_like_key(text: str) -> bool:
    """Heuristic: does *text* look like a YAML mapping key?"""
    text = text.strip().strip('"').strip("'")
    if not text:
        return False
    return all(c.isalnum() or c in '_-' for c in text)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_context_routes(routes_path: Path) -> list:
    """Validate context routes YAML and return list of error strings."""
    errors = []

    if not routes_path.exists():
        return [f'Context routes file not found: {routes_path}']

    try:
        with open(routes_path) as f:
            content = f.read()
        routes_data = parse_simple_yaml(content)
    except Exception as e:
        return [f'Failed to parse YAML: {e}']

    if not isinstance(routes_data, dict):
        return ['Routes root must be a mapping']

    # -- Top-level scalars ---------------------------------------------------
    if 'version' not in routes_data:
        errors.append('Missing top-level "version" field')
    elif routes_data['version'] != 1:
        errors.append(f'Unsupported version: {routes_data["version"]}')

    if 'routing_strategy' not in routes_data:
        errors.append('Missing top-level "routing_strategy" field')

    # -- Routes section ------------------------------------------------------
    if 'routes' not in routes_data:
        errors.append('Missing "routes" section')
        return errors

    routes = routes_data['routes']
    if not isinstance(routes, list):
        errors.append('"routes" must be a list')
        return errors

    if len(routes) == 0:
        errors.append('"routes" list is empty')
        return errors

    seen_ids = set()
    for i, route in enumerate(routes):
        prefix = f'routes[{i}]'

        if not isinstance(route, dict):
            errors.append(f'{prefix}: must be a mapping')
            continue

        # Required fields.
        missing = REQUIRED_ROUTE_FIELDS - set(route.keys())
        if missing:
            errors.append(f'{prefix}: missing required fields: {sorted(missing)}')
            continue

        # ID.
        route_id = route.get('id')
        if not isinstance(route_id, str) or not route_id.strip():
            errors.append(f'{prefix}: "id" must be a non-empty string')
        else:
            if route_id in seen_ids:
                errors.append(f'{prefix}: duplicate id "{route_id}"')
            seen_ids.add(route_id)

        # match must be non-empty.
        match = route.get('match')
        if match is None or (isinstance(match, (dict, list)) and len(match) == 0):
            errors.append(f'{prefix}: "match" must not be empty')

        # load must be non-empty list.
        load = route.get('load')
        if load is None:
            errors.append(f'{prefix}: "load" must not be empty')
        elif isinstance(load, list) and len(load) == 0:
            errors.append(f'{prefix}: "load" must not be empty')

        # do_not_load must be present to prevent over-loading.
        do_not_load = route.get('do_not_load')
        if do_not_load is None:
            errors.append(
                f'{prefix}: missing "do_not_load" -- every route must declare what NOT to load'
            )
        elif isinstance(do_not_load, list) and len(do_not_load) == 0:
            errors.append(f'{prefix}: "do_not_load" must not be empty')

        # load must not contain full-scope fallback patterns.
        if isinstance(load, list):
            for pattern in FORBIDDEN_FULL_LOAD_PATTERNS:
                if pattern in load:
                    errors.append(
                        f'{prefix}: "load" contains forbidden full-scope pattern "{pattern}"'
                    )

    # Must have at least 4 routes covering different concerns.
    if len(seen_ids) < 4:
        errors.append(f'Expected at least 4 routes, found {len(seen_ids)}')

    return errors


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    routes_path = repo_root / 'harness' / 'context' / 'routes.yaml'

    errors = validate_context_routes(routes_path)

    if errors:
        print('Context routes validation failed:')
        for err in errors:
            print(f'  - {err}')
        sys.exit(1)

    print('context routes ok')


if __name__ == '__main__':
    main()
