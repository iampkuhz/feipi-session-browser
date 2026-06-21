"""Qoder credit parser：解析 Qoder credit events。

从 Qoder session 数据中提取 credit 消耗信息。
"""

from __future__ import annotations


def parse_qoder_credit_events(events: list[dict] | None) -> dict:
    """解析 Qoder credit events。

    Args:
        events: credit event 列表，每个事件包含 type, delta, model, timestamp 等

    Returns:
        {"total_credits": float, "by_model": dict, "precision": str, "note": str}
    """
    if not events:
        return {
            'total_credits': None,
            'by_model': {},
            'precision': 'unavailable',
            'note': '无 credit events',
        }

    total = 0.0
    by_model: dict[str, float] = {}

    for ev in events:
        if not isinstance(ev, dict):
            continue
        delta = ev.get('delta')
        try:
            delta = float(delta) if delta is not None else 0.0
        except (TypeError, ValueError):
            continue
        total += delta
        model = ev.get('model', 'unknown')
        by_model[model] = by_model.get(model, 0.0) + delta

    return {
        'total_credits': total,
        'by_model': by_model,
        'precision': 'exact' if any(e.get('type') == 'exact' for e in events) else 'estimated',
        'note': f'Qoder credit: {len(events)} events, total {total:.2f} credits',
    }
