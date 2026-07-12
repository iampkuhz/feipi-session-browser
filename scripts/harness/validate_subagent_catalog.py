#!/usr/bin/env python3
"""本模块负责执行 `validate_subagent_catalog` 对应的确定性仓库检查。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

import sys
from pathlib import Path

REQUIRED_FIELDS = {
    'id',
    'kind',
    'read_scope',
    'write_scope',
    'forbidden_scope',
    'trigger_rules',
    'validation_cmds',
    'retry_policy',
}

LIST_FIELDS = {'read_scope', 'write_scope', 'forbidden_scope', 'trigger_rules', 'validation_cmds'}

VALID_KINDS = {'readonly-analysis', 'restricted-writer', 'verification-only'}


# 解析simple YAML。
def parse_simple_yaml(content: str) -> dict:
    """参数：
        content: 要写入的文本内容。

    返回：
        结果映射。
    """
    lines = content.split('\n')
    result = {}
    current_section = None
    current_list_item = None
    in_subagents = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        lstripped = line.lstrip()

        # 跳过空 行 和 comments。
        if not stripped or stripped.startswith('#'):
            i += 1
            continue

        # 计算indentation。
        indent = len(line) - len(line.lstrip())

        if indent == 0 and ':' in stripped:
            # 保存previous 列表 item 如果 any。
            if current_list_item is not None and in_subagents:
                if not isinstance(result.get('subagents'), list):
                    result['subagents'] = []
                result['subagents'].append(current_list_item)
                current_list_item = None

            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()

            if value:
                result[key] = parse_value(value)
                current_section = None
                in_subagents = False
            else:
                # 开始解析嵌套结构。
                result[key] = {}
                current_section = key
                in_subagents = key == 'subagents'
                current_list_item = None

        elif current_section and indent > 0:
            # 读取 subagents 下的列表项。
            if in_subagents and lstripped.startswith('- '):
                # 保存previous 列表 item 如果 any。
                if current_list_item is not None:
                    if not isinstance(result.get('subagents'), list):
                        result['subagents'] = []
                    result['subagents'].append(current_list_item)

                # 启动new 列表 item。
                current_list_item = {}
                item_content = lstripped[2:]  # 移除列表项前缀。
                if ':' in item_content:
                    key, _, value = item_content.partition(':')
                    current_list_item[key.strip()] = parse_value(value.strip())

            # 合并列表项的续行。
            elif current_list_item is not None and indent >= 4:
                if ':' in lstripped:
                    key, _, value = lstripped.partition(':')
                    key = key.strip()
                    value = value.strip()

                    if value:
                        current_list_item[key] = parse_value(value)
                    else:
                        # 启动of 列表 值。
                        current_list_item[key] = []
                        # 收集列表 items。
                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j]
                            next_stripped = next_line.rstrip()
                            next_lstripped = next_line.lstrip()
                            if not next_stripped or next_stripped.startswith('#'):
                                j += 1
                                continue
                            next_indent = len(next_line) - len(next_line.lstrip())
                            if next_indent <= indent:
                                break
                            if next_lstripped.startswith('- '):
                                item_val = next_lstripped[2:].strip()
                                current_list_item[key].append(parse_value(item_val))
                            j += 1
                        i = j - 1

            # Nested 映射 (不 in subagents 列表)。
            elif ':' in lstripped and not in_subagents:
                key, _, value = lstripped.partition(':')
                key = key.strip()
                value = value.strip()
                if isinstance(result.get(current_section), dict):
                    result[current_section][key] = parse_value(value) if value else {}

        i += 1

    # 保存last 列表 item。
    if current_list_item is not None:
        if not isinstance(result.get('subagents'), list):
            result['subagents'] = []
        result['subagents'].append(current_list_item)

    return result


# 解析值。
def parse_value(value: str):
    """参数：
    value: value 参数。
    """
    if not value:
        return None

    # 空 列表。
    if value == '[]':
        return []

    # 移除quotes。
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    # 布尔值。
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False

    # 数字。
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    # 字符串。
    return value


# 验证catalog。
def validate_catalog(catalog_path: Path) -> list[str]:
    """参数：
        catalog_path: 待检查的路径。

    返回：
        结果列表。
    """
    errors = []

    if not catalog_path.exists():
        return [f'Catalog file not found: {catalog_path}']

    try:
        with open(catalog_path) as f:
            content = f.read()
        catalog = parse_simple_yaml(content)
    except Exception as e:
        return [f'Failed to parse YAML: {e}']

    if not isinstance(catalog, dict):
        return ['Catalog root must be a mapping']

    # 检查顶层目录结构。
    if 'version' not in catalog:
        errors.append('Missing top-level "version" field')
    elif catalog['version'] != 1:
        errors.append(f'Unsupported version: {catalog["version"]}')

    if 'execution' not in catalog:
        errors.append('Missing "execution" section')
    else:
        exec_cfg = catalog['execution']
        if not isinstance(exec_cfg, dict):
            errors.append('"execution" must be a mapping')
        else:
            if exec_cfg.get('llm_concurrency') != 1:
                errors.append('execution.llm_concurrency must be 1')

    if 'subagents' not in catalog:
        errors.append('Missing "subagents" section')
        return errors

    subagents = catalog['subagents']
    if not isinstance(subagents, list):
        errors.append('"subagents" must be a list')
        return errors

    if len(subagents) == 0:
        errors.append('"subagents" list is empty')
        return errors

    # 检查each subagent。
    seen_ids = set()
    for i, sa in enumerate(subagents):
        prefix = f'subagents[{i}]'

        if not isinstance(sa, dict):
            errors.append(f'{prefix}: must be a mapping')
            continue

        # 检查必需 fields。
        missing = REQUIRED_FIELDS - set(sa.keys())
        if missing:
            errors.append(f'{prefix}: missing required fields: {sorted(missing)}')
            continue

        # 检查id。
        sa_id = sa['id']
        if not isinstance(sa_id, str) or not sa_id.strip():
            errors.append(f'{prefix}: "id" must be a non-empty string')
        else:
            if sa_id in seen_ids:
                errors.append(f'{prefix}: duplicate id "{sa_id}"')
            seen_ids.add(sa_id)

        # 检查kind。
        kind = sa['kind']
        if kind not in VALID_KINDS:
            errors.append(f'{prefix}: invalid kind "{kind}", must be one of {sorted(VALID_KINDS)}')

        # 检查列表 fields。
        for field in LIST_FIELDS:
            val = sa.get(field)
            if val is not None and not isinstance(val, list):
                errors.append(f'{prefix}: "{field}" must be a list')

        # 检查retry_policy。
        retry = sa.get('retry_policy')
        if not isinstance(retry, str) or not retry.strip():
            errors.append(f'{prefix}: "retry_policy" must be a non-empty string')

    return errors


# 解析命令行参数并运行脚本入口。
def main():
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    repo_root = Path(__file__).resolve().parent.parent.parent
    catalog_path = repo_root / 'harness' / 'subagents' / 'catalog.yaml'

    errors = validate_catalog(catalog_path)

    if errors:
        print('Subagent catalog validation failed:')
        for err in errors:
            print(f'  - {err}')
        sys.exit(1)

    print('subagent catalog ok')


if __name__ == '__main__':
    main()
