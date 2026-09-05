# 合成 Session 样本约束

完整会话 JSONL 不属于文档，也不能作为生产 Gate 输入。仓库只在
`java/tests/fixtures/session_samples/synthetic/` 保留固定、最小、脱敏的合成输入。

这些 fixture 覆盖两种公开源格式的最小语义：

- Claude Code：user/assistant、usage、tool use/result 关联。
- Codex：parent/child metadata、message、tool call/output、token usage。

`SessionSampleIntegrationTest` 用真实 source adapter 和 normalization engine 读取这些文件，
断言 canonical schema、source 关系与 byte-for-byte 确定性。fixture 只能使用固定 ID、固定时间、
相对 synthetic 路径和占位内容；禁止提交 normalized 生成物、真实 prompt、tool output、token、
email 或本地绝对路径。
