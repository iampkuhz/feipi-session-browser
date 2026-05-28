#!/usr/bin/env python3
"""生成 100 轮合成 session fixture，用于性能测试。"""

import json
import os
import random
import string

FIXTURE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_ID = "long-session-001"
PROJECT_KEY = "test-hifi-project"
NUM_ROUNDS = 100

TOOLS = ["Read", "Bash", "Write", "Edit", "Grep", "LS", "Agent", "Find"]
TOPICS = [
    "Fix the login page layout regression on mobile devices",
    "Add unit tests for the authentication module",
    "Refactor the database connection pooling logic",
    "Implement pagination for the search results endpoint",
    "Update the CI pipeline to use Python 3.12",
    "Add input validation to the user registration form",
    "Investigate and fix the memory leak in the cache layer",
    "Create a dashboard widget for error rate monitoring",
    "Migrate the legacy API endpoints to the new router",
    "Add rate limiting to the public API endpoints",
    "Implement dark mode toggle for the settings page",
    "Optimize the SQL queries for the report generation",
    "Add retry logic for flaky third-party API calls",
    "Review and update the API documentation for v2",
    "Implement file upload with progress indicator",
    "Add comprehensive error handling to the payment flow",
    "Refactor the notification system to use async workers",
    "Create integration tests for the webhook endpoints",
    "Add caching layer to the product catalog API",
    "Implement role-based access control for admin routes",
]

def rand_id(prefix=""):
    return f"{prefix}{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"

def gen_tool_results(tool_uses):
    """生成与 tool_use ID 匹配的 tool result 条目。"""
    results = []
    for tu in tool_uses:
        tu_id = tu["id"]
        tu_name = tu["name"]
        if tu_name == "Bash":
            content = f"exit_code: 0\nstdout: {''.join(random.choices(string.ascii_lowercase + string.digits, k=40))}"
        elif tu_name == "Read":
            content = f"File contents (truncated): {''.join(random.choices(string.ascii_lowercase, k=80))}"
        elif tu_name == "LS":
            content = f"src/\n  __init__.py\n  main.py\n  utils.py\ntests/\n  test_main.py"
        elif tu_name == "Write":
            content = "File written successfully."
        elif tu_name == "Edit":
            content = "Edit applied successfully."
        elif tu_name == "Grep":
            content = f"src/main.py:42: {''.join(random.choices(string.ascii_lowercase, k=50))}"
        elif tu_name == "Agent":
            content = "Subagent completed successfully. summary: task done"
        elif tu_name == "Find":
            content = f"src/{''.join(random.choices(string.ascii_lowercase, k=10))}.py\nlib/{''.join(random.choices(string.ascii_lowercase, k=8))}.py"
        else:
            content = "ok"
        results.append({
            "tool_use_id": tu_id,
            "type": "tool_result",
            "content": [{"type": "text", "content": content}]
        })
    return results

def gen_tool_uses(count):
    """生成 tool_use 块。"""
    tools = random.sample(TOOLS, min(count, len(TOOLS)))
    return [
        {
            "type": "tool_use",
            "name": name,
            "input": {"path": f"/src/{name.lower()}.py"} if name in ("Read", "Write") else {"command": f"echo hello"} if name == "Bash" else {},
            "id": rand_id(f"tool_{name.lower()}_")
        }
        for name in tools
    ]

def main():
    session_lines = []
    base_ts = 1713952800000  # 2024-04-24T10:00:00Z

    # history.jsonl
    history = {
        "sessionId": SESSION_ID,
        "project": PROJECT_KEY,
        "display": f"Long session with {NUM_ROUNDS} rounds for performance testing",
        "timestamp": base_ts
    }
    with open(os.path.join(FIXTURE_DIR, "history.jsonl"), "w") as f:
        f.write(json.dumps(history) + "\n")

    # Session JSONL 文件
    ts_offset = 0
    for round_idx in range(NUM_ROUNDS):
        topic = TOPICS[round_idx % len(TOPICS)]
        if round_idx >= len(TOPICS):
            topic = f"Round {round_idx + 1}: {topic}"

        # 1. 用户消息
        ts_offset += random.randint(5, 30)
        user_ts = f"2026-04-24T{10 + ts_offset // 3600:02d}:{(ts_offset % 3600) // 60:02d}:{ts_offset % 60:02d}.000Z"
        session_lines.append(json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": topic
            },
            "timestamp": user_ts,
            "cwd": "/Users/test/projects/feipi-session-browser",
            "entrypoint": "cli",
            "gitBranch": "main"
        }))

        # 2. 助手 LLM 调用（含可选 tool uses）
        ts_offset += random.randint(2, 15)
        llm_ts = f"2026-04-24T{10 + ts_offset // 3600:02d}:{(ts_offset % 3600) // 60:02d}:{ts_offset % 60:02d}.000Z"
        input_tokens = random.randint(500, 5000)
        cache_read = random.randint(0, input_tokens // 2) if round_idx > 10 else 0
        cache_write = random.randint(200, 2000) if round_idx < 20 else 0
        output_tokens = random.randint(50, 500)

        # 生成 tool uses（有时为纯文本响应）
        if random.random() < 0.3:
            content_blocks = [{"type": "text", "text": f"I'll work on {topic.lower()}."}]
            stop_reason = "end_turn"
        else:
            tool_uses = gen_tool_uses(random.randint(1, 4))
            content_blocks = [
                {"type": "text", "text": f"Let me explore the codebase first."},
                *tool_uses
            ]
            stop_reason = "tool_use"

        usage = {
            "input_tokens": input_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_write,
            "output_tokens": output_tokens
        }
        if stop_reason == "tool_use":
            usage["stop_reason"] = "tool_use"

        session_lines.append(json.dumps({
            "type": "assistant",
            "message": {
                "model": "claude-sonnet-4-20250514",
                "role": "assistant",
                "content": content_blocks,
                "usage": usage,
                "stop_reason": stop_reason
            },
            "timestamp": llm_ts
        }))

        # 3. 工具结果（如果有 tool_uses 输出）
        all_tool_uses = [b for b in content_blocks if b["type"] == "tool_use"]

        if all_tool_uses:
            ts_offset += random.randint(3, 10)
            result_ts = f"2026-04-24T{10 + ts_offset // 3600:02d}:{(ts_offset % 3600) // 60:02d}:{ts_offset % 60:02d}.000Z"
            tool_results = gen_tool_results(all_tool_uses)
            session_lines.append(json.dumps({
                "type": "user",
                "message": {
                    "role": "user",
                    "content": tool_results
                },
                "timestamp": result_ts,
                "cwd": "/Users/test/projects/feipi-session-browser",
                "entrypoint": "cli",
                "gitBranch": "main"
            }))

    # 写入 session 文件
    session_path = os.path.join(FIXTURE_DIR, "projects", PROJECT_KEY, f"{SESSION_ID}.jsonl")
    with open(session_path, "w") as f:
        f.write("\n".join(session_lines) + "\n")

    print(f"Generated {len(session_lines)} JSONL lines for {NUM_ROUNDS} rounds")
    print(f"Session file: {session_path}")
    print(f"History file: {os.path.join(FIXTURE_DIR, 'history.jsonl')}")

if __name__ == "__main__":
    main()
