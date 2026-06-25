#!/usr/bin/env python3
"""Validate trigger-policy.yaml structure and required fields.

Only uses Python stdlib - implements minimal YAML parsing for trigger policy structure.
"""

import sys
from pathlib import Path


REQUIRED_RULE_FIELDS = {'id', 'when', 'require'}

EXPECTED_RULE_IDS = {
    'non_trivial_change_requires_openspec',
    'enum_external_value_guard',
    'source_adapter_contract_guard',
    'normalized_artifact_contract_guard',
    'build_logic_guard',
    'docs_information_density_guard',
    'stop_gate',
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
    """Parse the trigger-policy YAML structure.

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

        # Skip empty lines and comments.
        if not stripped or lstripped.startswith('#'):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # Top-level key (indent == 0).
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
                # Block follows -- determine whether it is a list or mapping.
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

    Strategy: split each list-item group into direct keys (at ``base_indent+2``)
    and their block content (anything deeper).  Parse each block independently
    via ``_parse_block_value``.
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
                # Determine block content indent from first content line.
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
    # Find first non-empty line to determine type.
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
            if ':' in val and _looks_like_mapping_key(val.partition(':')[0]):
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
    sub_indent = None

    def _flush():
        nonlocal current_key, sub_lines, sub_indent
        if current_key is not None:
            if sub_lines:
                effective = sub_indent or base_indent + 2
                result[current_key] = _parse_block_value(sub_lines, effective)
            else:
                result[current_key] = {}
        current_key = None
        sub_lines = []
        sub_indent = None

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
            if sub_indent is None:
                sub_indent = indent
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


def _looks_like_mapping_key(text: str) -> bool:
    """Heuristic: does *text* look like ``key: ...``?"""
    text = text.strip().strip('"').strip("'")
    if ':' not in text:
        return False
    k = text.partition(':')[0].strip()
    return bool(k) and all(c.isalnum() or c in '_-' for c in k)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_trigger_policy(policy_path: Path) -> list:
    """Validate trigger-policy.yaml and return list of error strings."""
    errors = []

    if not policy_path.exists():
        return [f'Trigger policy file not found: {policy_path}']

    try:
        with open(policy_path) as f:
            content = f.read()
        policy = parse_simple_yaml(content)
    except Exception as e:
        return [f'Failed to parse YAML: {e}']

    if not isinstance(policy, dict):
        return ['Policy root must be a mapping']

    # -- Top-level scalars ---------------------------------------------------
    if 'version' not in policy:
        errors.append('Missing top-level "version" field')
    elif policy['version'] != 1:
        errors.append(f'Unsupported version: {policy["version"]}')

    if 'policy_owner' not in policy:
        errors.append('Missing top-level "policy_owner" field')

    if 'llm_concurrency' not in policy:
        errors.append('Missing top-level "llm_concurrency" field')

    # -- Rules section -------------------------------------------------------
    if 'rules' not in policy:
        errors.append('Missing "rules" section')
        return errors

    rules = policy['rules']
    if not isinstance(rules, list):
        errors.append('"rules" must be a list')
        return errors

    if len(rules) == 0:
        errors.append('"rules" list is empty')
        return errors

    seen_ids = set()
    for i, rule in enumerate(rules):
        prefix = f'rules[{i}]'

        if not isinstance(rule, dict):
            errors.append(f'{prefix}: must be a mapping')
            continue

        # Required fields.  A rule must have ``id``, ``when``, and at least
        # one of ``require`` or ``require_fields`` (some rules use
        # ``require_fields`` + ``reject`` instead of a ``require`` list).
        missing = {'id', 'when'} - set(rule.keys())
        if 'require' not in rule and 'require_fields' not in rule:
            missing.add('require')
        if missing:
            errors.append(f'{prefix}: missing required fields: {sorted(missing)}')
            continue

        # ID.
        rule_id = rule.get('id')
        if not isinstance(rule_id, str) or not rule_id.strip():
            errors.append(f'{prefix}: "id" must be a non-empty string')
        else:
            if rule_id in seen_ids:
                errors.append(f'{prefix}: duplicate id "{rule_id}"')
            seen_ids.add(rule_id)

        # when must be non-empty.
        when = rule.get('when')
        if when is None or (isinstance(when, (dict, list)) and len(when) == 0):
            errors.append(f'{prefix}: "when" must not be empty')

        # require (or require_fields) must be non-empty.
        require = rule.get('require')
        require_fields = rule.get('require_fields')
        if require is not None:
            if isinstance(require, list) and len(require) == 0:
                errors.append(f'{prefix}: "require" must not be empty')
        elif require_fields is not None:
            if isinstance(require_fields, list) and len(require_fields) == 0:
                errors.append(f'{prefix}: "require_fields" must not be empty')
        # If neither is present, the earlier required-fields check catches it.

    # -- Coverage: all expected rule IDs present -----------------------------
    missing_ids = EXPECTED_RULE_IDS - seen_ids
    if missing_ids:
        errors.append(f'Missing expected rule ids: {sorted(missing_ids)}')

    if len(seen_ids) < 6:
        errors.append(f'Expected at least 6 rules, found {len(seen_ids)}')

    return errors


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    policy_path = repo_root / 'harness' / 'rules' / 'trigger-policy.yaml'

    errors = validate_trigger_policy(policy_path)

    if errors:
        print('Trigger policy validation failed:')
        for err in errors:
            print(f'  - {err}')
        sys.exit(1)

    print('trigger-policy ok')


if __name__ == '__main__':
    main()
