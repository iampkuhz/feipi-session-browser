---
name: feipi-privacy-redaction-dev
disable-model-invocation: true
description: 用于 request/response、token、路径、环境变量、真实 session 样本展示和测试时的隐私脱敏规则；纯 UI 排版不要使用。
---

# 隐私与脱敏

本 skill 为涉及 request/response 展示、token 处理、路径输出、环境变量引用、真实 session 样本和测试 fixture 的场景提供固定脱敏执行流程。核心原则：敏感数据默认隐藏、fixture 必须 synthetic、gate 拦截真实数据入仓。

## 何时使用

- 展示或导出 request/response 数据时。
- 处理 token、api key、authorization header、cookie 等凭证字段时。
- 输出包含本地绝对路径（`~/.claude`、`~/.codex`、`~/.qoder`）的日志或文档时。
- 创建测试 fixture 或样例数据时。
- 复制用户粘贴的内容到仓库时。
- 运行隐私相关门禁时。

## 不要何时使用

- 纯 UI 排版或样式调整 — 使用对应功能 skill（如 `feipi-session-detail-ui-dev`）。
- 功能开发前置设计 — 使用 `feipi-java-feature-dev` 或 `feipi-session-ingestion-dev`。
- OpenSpec 编排 — 使用 `feipi-openspec-orchestrate-change`。
- 不需要展示敏感数据的产品逻辑修改。
- 纯内部重构，不涉及数据展示或 fixture。

## 输入最小化

只读取以下必要片段：

1. 涉及敏感字段的代码片段或配置。
2. 测试 fixture 文件（仅检查是否 synthetic）。
3. 导出或展示逻辑中的字段映射。
4. 隐私 gate 的脚本和输出。

不要全仓库扫描。不要读取真实 session 数据。不要复制真实 token 或密钥。

## 执行步骤

1. **判断数据来源**：确认数据来自 fixture、真实 session、生成样例还是用户粘贴。不同来源适用不同脱敏策略。
2. **标注敏感字段**：识别 token、api key、authorization、cookie、本地路径、邮箱、原始 prompt、response 中的敏感内容。参考 `references/sensitive-fields.md`。
3. **检查 UI 默认是否隐藏敏感字段**：确认前端展示默认遮盖或省略敏感字段，不依赖用户手动操作。参考 `references/redaction-policy.md`。
4. **检查导出是否遵循当前脱敏策略**：确认导出逻辑（JSON、HTML、日志）对敏感字段执行替换或省略。
5. **检查测试 fixture 是否 synthetic**：确认 `tests/` 下的 fixture 文件使用合成数据，不包含真实 session 内容。参考 `references/fixture-policy.md`。
6. **禁止复制 `~/.claude`、`~/.codex`、`~/.qoder` 原始文件入仓**：检查变更中没有从用户 home 目录复制真实文件。
7. **对必须展示的字段给最小化片段**：只展示字段名前缀或占位符（如 `sk-***`、`<REDACTED>`），不展示完整值。
8. **增加 gate 或 fixture contract**：如果需要新增检查，在 `scripts/checks/privacy/` 创建对应
   leaf check，并接入共享 check registry。
9. **运行隐私 gate**：执行 `repository.no-real-session-fixtures` 和 `security.secret-like-content`，确认无敏感数据泄露。
10. **输出风险和残留敏感字段**：在报告中列出仍可能存在的风险，如第三方 API 返回内容中的用户数据。

## 文件边界

- Skill 源目录：`skills/authoring/feipi-privacy-redaction-dev/`。
- 隐私 gate 脚本：`shared check `repository.no-real-session-fixtures``、`shared check `security.secret-like-content``。
- 测试 fixture 目录：`tests/fixtures/synthetic/`。
- 配置引用：`harness/skill-registry.yaml`、`harness/manifest.yaml`。

不要跨边界修改产品脱敏逻辑。不要修改真实 session 数据。不要重新引入平台 Hook 或真实运行数据。

## 验证门禁

- `python3 -m scripts.checks repository.no-real-session-fixtures` — 检测真实 session fixture。
- `python3 -m scripts.checks security.secret-like-content` — 检测类密钥内容。
- `python3 -m scripts.checks agent.skill-registry` — registry 完整性。
- `python3 scripts/harness/validate_harness_structure.py` — minimal harness 结构完整性。
- `bash scripts/harness/doctor.sh` — 全量环境体检。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 涉及的敏感字段列表。
- 脱敏策略（隐藏/替换/省略）。
- fixture 是否 synthetic。
- 隐私 gate 运行结果。
- 残留风险和后续 TODO。
