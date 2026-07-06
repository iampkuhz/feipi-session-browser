# Proposal: Complete TODO normalization quality contracts

## Problem

`TODO.md` 中剩余可闭环项分散在 normalized artifact 结构、Codex subagent 归属、session samples 质量门、Python 环境契约、warning-free 和中文注释门禁。当前样例集成测试失败但被 ignoreFailures 掩盖，Codex child rollout 只产生诊断而未物化为 subagent calls/tools，Python runtime 只声明最低版本，脚本/前端注释语言门禁覆盖不足。

## Scope

- 结构化 normalized session、source、diagnostic 和 source relation 数据。
- 物化有稳定证据的 Codex child rollout subagent calls/tools。
- 让 docs/session-samples 样例集成测试成为阻断质量门。
- 建立 Python 3.12 minor runtime 契约并统一 doctor/python_env 校验。
- 去除 known warning 通过语义，扩展中文注释门禁覆盖。
- 更新 TODO 勾选状态，仅勾选本次实际闭环项。

## Non-goals

- 不实现 Session Detail UI 四卡布局。
- 不处理 qa-verify 长时间不停的 Codex app 行为。
- 不扩大 PMD/Checkstyle/Spotless/ArchUnit 覆盖范围。
- 不做 modal UI 结构改造。

## User impact

开发者能用样例和质量门捕捉 normalized/subagent/Python/comment/warning 漂移；Session Detail 与索引消费 normalized artifact 时获得更稳定的结构化字段。

## Validation strategy

运行 OpenSpec 验证、相关 Gradle test/sampleIntegrationTest、Python env/doctor/comment checks，并用 required quality gates 收口。
