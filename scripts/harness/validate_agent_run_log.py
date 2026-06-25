#!/usr/bin/env python3
"""校验 agent run log 的基本结构完整性。

检查必填段落和字段是否存在。只用 Python stdlib。

用法：
    python3 validate_agent_run_log.py <log-file>
    python3 validate_agent_run_log.py --help

退出码：
    0 — 校验通过
    1 — 校验失败或参数错误
"""

import argparse
import re
import sys
from pathlib import Path


REQUIRED_SECTIONS = [
    "Run Metadata",
    "Handoff",
    "Timeline",
    "Rate Limit / Retry",
    "Completion",
]

REQUIRED_METADATA_FIELDS = [
    "run_id",
    "task_id",
    "parent_agent",
    "child_agent",
]

VALID_STATUSES = {"PASS", "FAIL", "BLOCKED", "BLOCKED_RETRYABLE"}

VALID_VALIDATION_RESULTS = {"PASS", "FAIL", "NOT_RUN"}


def parse_metadata(section_content: str) -> dict[str, str]:
    """从 Run Metadata 段落解析 key: value 对。"""
    metadata = {}
    for line in section_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^-\s*([a-z_]+):\s*(.*)", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            metadata[key] = value
    return metadata


def parse_completion_section(section_content: str) -> dict:
    """从 Completion 段落解析 YAML-like 输出结构。"""
    result = {"has_status": False, "has_changed_files": False,
              "has_validation": False, "status_value": None}

    for line in section_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("status:"):
            result["has_status"] = True
            value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            result["status_value"] = value
        elif stripped.startswith("changed_files:"):
            result["has_changed_files"] = True
        elif stripped.startswith("validation:"):
            result["has_validation"] = True

    return result


def split_sections(content: str) -> dict[str, str]:
    """将 markdown 按 ## 标题拆分为 {标题: 内容}。"""
    sections = {}
    current_heading = None
    current_lines = []

    for line in content.splitlines():
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines)
            current_heading = heading_match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines)

    return sections


def validate_log(log_path: Path) -> list[str]:
    """校验 agent run log 文件，返回错误列表。"""
    errors = []

    if not log_path.exists():
        return [f"日志文件不存在: {log_path}"]

    try:
        content = log_path.read_text(encoding="utf-8")
    except Exception as e:
        return [f"无法读取日志文件: {e}"]

    if not content.strip():
        return ["日志文件为空"]

    sections = split_sections(content)

    # 检查必填段落
    for section_name in REQUIRED_SECTIONS:
        if section_name not in sections:
            errors.append(f"缺少必填段落: ## {section_name}")

    # 检查 Run Metadata 必填字段
    if "Run Metadata" in sections:
        metadata = parse_metadata(sections["Run Metadata"])
        for field in REQUIRED_METADATA_FIELDS:
            if field not in metadata:
                errors.append(f"Run Metadata 缺少必填字段: {field}")
            elif not metadata[field]:
                errors.append(f"Run Metadata 字段 {field} 的值为空")
    else:
        # Run Metadata 段落缺失时，无法检查字段
        pass

    # 检查 Timeline 段落是否有表格
    if "Timeline" in sections:
        timeline = sections["Timeline"]
        if "|" not in timeline:
            errors.append("Timeline 段落缺少表格格式（应包含 | 分隔的列）")

    # 检查 Rate Limit / Retry 段落是否有表格
    if "Rate Limit / Retry" in sections:
        retry = sections["Rate Limit / Retry"]
        if "|" not in retry:
            errors.append("Rate Limit / Retry 段落缺少表格格式（应包含 | 分隔的列）")

    # 检查 Completion 段落
    if "Completion" in sections:
        completion = parse_completion_section(sections["Completion"])
        if not completion["has_status"]:
            errors.append("Completion 段落缺少 status 字段")
        elif completion["status_value"] and completion["status_value"] not in VALID_STATUSES:
            errors.append(
                f"Completion status 值无效: \"{completion['status_value']}\"，"
                f"必须是 {sorted(VALID_STATUSES)} 之一"
            )
        if not completion["has_changed_files"]:
            errors.append("Completion 段落缺少 changed_files 字段")
        if not completion["has_validation"]:
            errors.append("Completion 段落缺少 validation 字段")

    return errors


def main():
    parser = argparse.ArgumentParser(
        description="校验 agent run log 的基本结构完整性（必填段落和字段是否存在）。",
        epilog="示例: python3 validate_agent_run_log.py tmp/agent_state/migration/P01-T03.log.md",
    )
    parser.add_argument(
        "log_file",
        type=str,
        help="要校验的 agent run log 文件路径",
    )
    args = parser.parse_args()

    log_path = Path(args.log_file)
    if not log_path.is_absolute():
        # 相对于仓库根目录解析
        repo_root = Path(__file__).resolve().parent.parent.parent
        log_path = repo_root / log_path

    errors = validate_log(log_path)

    if errors:
        print(f"Agent run log 校验失败 ({log_path}):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"agent run log ok ({log_path})")


if __name__ == "__main__":
    main()
