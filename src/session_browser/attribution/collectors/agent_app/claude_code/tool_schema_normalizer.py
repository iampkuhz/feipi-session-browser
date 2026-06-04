"""Claude Code tool schema normalizer：标准化 tool schema 输出。"""

from __future__ import annotations


def normalize_tool_schema(schema: dict | str | None) -> dict:
    """标准化 tool schema 为统一格式。

    Args:
        schema: 原始 schema（dict 或 JSON 字符串）

    Returns:
        标准化后的 schema dict
    """
    if schema is None:
        return {}

    if isinstance(schema, str):
        import json
        try:
            schema = json.loads(schema)
        except (json.JSONDecodeError, TypeError):
            return {"raw": schema}

    if not isinstance(schema, dict):
        return {"raw": str(schema)}

    return {
        "name": schema.get("name", ""),
        "description": schema.get("description", ""),
        "input_schema": schema.get("input_schema", {}),
    }


def compute_schema_hash(schema: dict) -> str:
    """计算 schema 的稳定 hash，用于去重和版本追踪。"""
    import hashlib
    import json
    canonical = json.dumps(schema, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
