# Session 标准样例

本目录存放用于人工确认的真实 session 标准样例。每个样例目录至少包含：

- `<session-id>.jsonl`：原始 session 数据，保留真实 id 文件名，作为可追溯证据和 parser 输入。
- `litellm_calls/`：可选；人工核对用的真实 API request/response 旁路证据。parser 和 `expected.normalized.jsonc` 生成不得依赖该目录。
- `expected.normalized.jsonc`：按当前 normalized session contract 提取出的标准结果；使用 JSONC 注释说明字段含义，便于人工确认。
- `README.md`：说明样例来源、覆盖场景、简化规则和确认状态。

目录按 agent 类型拆分，后续可继续添加：

- `claude-code/`
- `qoder/`
- `codex/`

这些样例用于建立人工确认基线。样例经人工确认后，不得在未明确点名的任务中顺手更新；如果 normalized contract 有意变更，需要先说明影响，再由人工确认新预期。

`expected.normalized.jsonc` 是人工审查文件，不作为运行时 artifact 格式。运行时 artifact 仍写入无注释 JSON。
