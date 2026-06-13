# Claude Code 样例：8a283a61-e3f0-4e8f-ba06-6711e2fcf2ed

## 文件

- `8a283a61-e3f0-4e8f-ba06-6711e2fcf2ed.jsonl`：复制自 `/Users/zhehan/.claude/projects/-Users-zhehan-Documents-tools-llm-feipi-agent-kit/8a283a61-e3f0-4e8f-ba06-6711e2fcf2ed.jsonl`。
- `litellm_calls/`：人工核对用的真实 API request/response 旁路证据；parser 和 `expected.normalized.jsonc` 生成不得依赖该目录。
- `expected.normalized.jsonc`：由 `session_browser.normalized.agents.claude_code.parse_claude_code_session_file()` 生成，校验时显式传入原始 project key，再添加逐字段注释，并通过去注释后的 `validate_normalized_session()` 校验。

## 样例摘要

- Agent：`claude_code`
- Session：`8a283a61-e3f0-4e8f-ba06-6711e2fcf2ed`
- 项目：`-Users-zhehan-Documents-tools-llm-feipi-agent-kit`
- 模型：`qwen3.7-plus`
- 原始 JSONL：31 行
- 标准结果：5 个 LLM call、5 个 tool execution
