# 仓库上下文路由

仅当任务需要跨目录理解仓库结构、选择验证目标、拆分 subagent 范围或判断本地运行态边界时读取本文件。普通单文件定位不要读取。

## 当前模块

| 路径 | 职责 |
|---|---|
| `src/session_browser/` | 产品源码、模板、静态资源、索引和归一化逻辑 |
| `tests/` | pytest、Playwright、fixture 和契约绑定 |
| `scripts/quality/` | required quality gates 和结构化 summary |
| `scripts/harness/` | 跨 Claude Code、Codex、Qoder 复用的 Stop 门禁和结构校验 |
| `scripts/claude_hooks/` | Claude Code hook runtime 的 Python 实现 |
| `.claude/`、`.codex/`、`.qoder/` | 工具入口、hooks、agents、薄配置 |
| `skills/` | 仓库共享 skill 真源 |
| `harness/` | agent 规约的渐进式加载扩展 |
| `openspec/` | 长期规格与本地待实施变更 |
| `docs/` | UI、验收契约、样例和 token 语义文档 |
| `java/` | Java 产品源码、测试和 Gradle 子项目 |
| `build-logic/` | 共享 Gradle 构建逻辑（convention plugins） |
| `gradle/` | Gradle wrapper 与依赖锁定、verification metadata 等构建供应链文件 |
| `.github/workflows/` | 跨平台 CI workflow（java-quality.yml） |

## 本地运行态

- `tmp/agent_logs/`、`tmp/quality/`、`data/`、`output/`、`.venv/`、`.pytest_cache/` 不应提交。
- `openspec/changes/*` 是本地工作态，默认不强行纳入 git。
- 真实 session data、token、密钥和个人配置不得进入提交。

## 读取策略

- 先用 `rg` 或 `find` 缩小范围，再读取文件片段。
- 需要 UI 规约时读取 `harness/context/ui-context.md`。
- 需要 subagent 规约时读取 `harness/workflow/subagent-execution.md`。
- 需要质量门语义时读取 `harness/quality/quality-gate-matrix.md` 和 `harness/quality/deterministic-quality-gate.md`。
