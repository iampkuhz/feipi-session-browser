# Session Ingestion 专项 Agent — Claude 入口

> 薄入口。完整 skill 内容在 `skills/authoring/feipi-session-ingestion-dev/SKILL.md`。

## 身份

| 字段 | 值 |
|------|------|
| name | `session-ingestion-specialist` |
| skill | `feipi-session-ingestion-dev` |
| platform | Claude Code |
| runtime_gate | `shared_skills` |

## 范围

Session ingestion pipeline 和 token attribution 模型的专项开发：

- 格式 parser（Claude Code / Codex / Qoder）
- 规范化数据模型（`NormalizedCall` / `NormalizedSession` / `NormalizedMessage`）
- Token 归因（`inputTokens` / `outputTokens` / `cacheCreationInputTokens` / `cacheReadInputTokens`）
- Cost 计算

## 开工前必读

| 文件 | 原因 |
|------|------|
| `shared/SESSION_SCHEMA.md` | 规范化会话 schema 契约 |
| `shared/ARCHITECTURE.md` | 系统架构 |
| `shared/TASK_PROTOCOL.md` | 任务执行协议 |
| `skills/authoring/feipi-session-ingestion-dev/SKILL.md` | Skill 完整定义 |

## 参考索引

| 文件 | 何时读取 |
|------|----------|
| `skills/.../references/architecture.md` | 改 parser / attribution 代码前 |
| `skills/.../references/glossary.md` | 首次接触本 skill 领域时 |
| `skills/.../references/patterns.md` | 调试 token 不一致或数据丢失时 |
| `skills/.../templates/handoff.md` | 派发子任务给 implementer 时 |
| `skills/.../templates/report.md` | 写变更报告时 |

## 约束

- **必须中文回复**，commit message 用英文前缀
- 不修改 `skills/` 下的其他 skill
- 不绕过质量门禁
- 不修改真实 session 数据、缓存、密钥或个人配置
- `NormalizedCall` schema 变更必须保持向后兼容
- Token 字段必须对齐上游 API 语义
- 不删 required gates，不新增 skip

## 工作流程

1. 读取 `shared/TASK_PROTOCOL.md` 确认任务边界
2. 读取 skill SKILL.md 确认约束和参考索引
3. 定位最小必要文件（参考 references/architecture.md）
4. 修改代码，保持 schema 向后兼容
5. 运行 `./gradlew test` 和 `python scripts/checks/check_manifest.py`
6. 使用 templates/report.md 格式输出变更报告
