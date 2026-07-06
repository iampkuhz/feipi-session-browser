# Design: Complete TODO normalization quality contracts

## Current state

Normalized artifact 顶层 session 和 diagnostics 使用裸 Map；CanonicalJsonWriter 输出 Java camelCase record 字段。Codex discovery 已过滤 subagent 列表展示，但 parse/normalize 未把 child rollout 合并为 subagent calls/tools。`sampleIntegrationTest` 被 ignoreFailures 掩盖。Python 环境仅检查 >=3.10。script comment gate 未覆盖 qoder hooks 和前端资源，doctor 仍有 known warning 文案。

## Proposed approach

新增结构化 domain 类型并保留 map 适配；CanonicalJsonWriter 使用 normalized v3 snake_case 外部协议。Codex parse 对 parent rollout 同目录 child rollout 做稳定证据合并，通过 SourceRecordRelation 携带 subagent 父子关系。sampleIntegrationTest 缺文件即失败并解析 Codex child rollouts，质量门加入 sample gate。Python contract 统一读取仓库 runtime 文件，要求 >=3.12,<3.13。doctor 不允许 warning 通过。注释语言检查扩展到 qoder hooks 和前端资源，并清理当前失败点。

## Risks

Canonical JSON 外部字段变化可能影响旧测试；通过同步 contract tests 和样例 expected 收敛。Codex child rollout 合并只使用显式 parent evidence，避免误归属。

## Rollback

回滚本 change 的 Java/Python/样例/TODO 修改；OpenSpec change 在归档前保持本地 runtime 状态。

## Validation

见 tasks.md 中每阶段命令。
