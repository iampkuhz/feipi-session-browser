# 负责范围

本 skill 覆盖以下场景的隐私脱敏规则：

- request/response 数据展示和导出。
- token、api key、authorization header、cookie 等凭证处理。
- 本地路径（`~/.claude`、`~/.codex`、`~/.qoder`）输出。
- 测试 fixture 创建和管理。
- 用户粘贴内容入仓检查。
- 日志和错误栈中的敏感信息。

## 禁止范围

- 纯 UI 排版或样式调整。
- 功能开发前置设计。
- OpenSpec 编排。
- 产品脱敏逻辑实现（本 skill 只提供规则，不改产品代码）。
- 真实 session 数据处理。

## 关键路径

- `skills/authoring/feipi-privacy-redaction-dev/` — skill 源目录。
- `shared check `repository.no-real-session-fixtures`` — 真实 session fixture 门禁。
- `shared check `security.secret-like-content`` — 类密钥内容门禁。
- `tests/fixtures/synthetic/` — synthetic fixture 目录。
- `harness/skill-registry.yaml` — skill registry。
- `harness/agent-runtime.manifest.yaml` — runtime manifest。

## 常见误区

- **误以为文档中的 `~/.claude` 路径是泄露**：文档中使用 `~/.claude` 占位符是允许的，只有真实 home 绝对路径才算泄露。
- **误以为所有 fixture 都需要 synthetic**：只有 `tests/` 和 `docs/` 下的 fixture 需要，产品代码中的示例数据按场景判断。
- **误以为 gate 只检查代码**：gate 同时检查文件路径和内容。
- **误以为短 token 不算敏感**：`sk-` 开头的任意长度 token 都视为敏感。

## 触发门禁

- `repository.no-real-session-fixtures` — 扫描测试 fixture、`docs/`、Qoder 配置和 harness report，检测真实 session 标记。
- `security.secret-like-content` — 扫描 `tests/`、`docs/`、`java/`、agent 平台入口和共享 skill，检测 `sk-` token、`Authorization: Bearer`、`api_key` 赋值。
- `agent.skill-registry` — 确认 skill registry 条目完整。
- `agent.runtime-manifest` — 确认 manifest 中 required skill 完整。
