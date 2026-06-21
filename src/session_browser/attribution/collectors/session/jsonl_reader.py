"""JSONL 事件流读取器：从 session JSONL 文件中提取结构化事件。

默认不读真实用户数据目录，只接受显式传入的路径或测试 fixture。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


def read_jsonl_events(file_path: str | Path) -> list[dict]:
    """读取 JSONL 文件，返回结构化事件列表。

    Args:
        file_path: JSONL 文件路径（测试 fixture 或显式传入）。

    Returns:
        每个 JSON 行解析后的 dict 列表，解析失败的行跳过并记录 debug 日志。
    """
    path = Path(file_path)
    if not path.exists():
        logger.debug('JSONL 文件不存在: %s', path)
        return []

    events: list[dict] = []
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        event['_line'] = line_num
                        events.append(event)
                except json.JSONDecodeError as exc:
                    logger.debug('JSONL 第 %d 行解析失败: %s', line_num, exc)
    except (OSError, PermissionError) as exc:
        logger.debug('无法读取 JSONL 文件 %s: %s', path, exc)

    return events


def iter_jsonl_events(file_path: str | Path) -> Iterator[dict]:
    """惰性迭代 JSONL 事件流。

    适合大文件，不需要一次性加载全部事件到内存。
    """
    path = Path(file_path)
    if not path.exists():
        return

    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        event['_line'] = line_num
                        yield event
                except json.JSONDecodeError:
                    pass
    except (OSError, PermissionError):
        return
