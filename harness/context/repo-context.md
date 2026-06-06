# 仓库上下文

## 概览

feipi-session-browser 是一个本地会话浏览器，用于索引和分析 Claude Code、Codex、Qoder 等本地 agent 的会话历史。它强调可追溯性、payload 可见性、UI 诊断和离线导出。

## 技术栈

- **后端**：Python 3（基于 Flask 的 Web 服务器）
- **前端**：HTML 模板 + CSS + 原生 JavaScript
- **测试**：Playwright（E2E）、pytest（单元测试）
- **数据**：JSONL 格式会话历史文件

## 目录结构

| 路径 | 用途 |
|------|------|
| `src/session_browser/` | 应用源码（服务器、模板、静态资源） |
| `tests/` | 单元测试、Playwright E2E 测试、fixture 数据 |
| `scripts/` | 构建、测试、harness 和质量门禁脚本 |
| `scripts/agent_hooks/` | Claude Code 生命周期钩子（PreToolUse、PostToolUse、Stop 等） |
| `scripts/quality/` | 仓库结构与健康度验证 |
| `scripts/harness/` | Harness 验证和 doctor 脚本 |
| `.claude/` | 项目级 Claude Code 配置、hooks、skills、commands、agents |
| `tmp/` | 本地 agent 状态（活跃变更、证据、任务账本）——不提交 |
| `openspec/` | OpenSpec 规格、变更、配置和 schema |
| `harness/` | Agent 流程文档、上下文包、模板 |
| `docs/` | 开发规范和 UI 规格 |
| `prompts/` | 输入提示词包——非权威入口；请通过 `/change` 路由 |

## 变更工作流

所有非平凡变更都通过 `/change <requirement-path>` 路由。详见 `harness/workflow/change-lifecycle.md` 和 `.claude/hooks/README.md`。

## 默认 Agent

| Agent | 用途 |
|-------|------|
| openspec-planner | 设计 OpenSpec 变更（proposal、design、tasks、spec 增量） |
| implementer | 从 tasks.md 执行单个有界的任务 |
| qa-verifier | 最终验证门禁（流程 + 技术正确性） |

`.claude/agents/specialty/` 下的 specialty agent 用于领域特定工作。

## 本地状态

以下文件被有意 `.gitignore`：
- `tmp/` — agent 状态（活跃变更、证据、任务结果）
- `openspec/changes/*` — 本地变更提议（除 `.gitkeep` 外）
- `reports/` — 非基线报告输出
- `test-results/`、`playwright-report/` — 测试运行器输出

## 质量门禁

运行 `bash scripts/harness/doctor.sh` 进行完整健康检查。

单独验证器：
```bash
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/quality/validate_repo_structure.py
```
