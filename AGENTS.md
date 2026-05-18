# Feipi Session Browser — 工程规则

本仓库是独立开发的本地会话浏览器，用于索引和分析 Claude Code、Codex、Qoder 等本地 agent 会话数据。

CLAUDE.md 是启动入口（薄），本文件是工程细则（厚）。两者不冲突：启动读 CLAUDE.md，深度工作读本文。

## 受保护根目录

以下路径受保护，编辑需有活跃 OpenSpec 变更（由 `.claude/` 内 PreToolUse hooks 强制执行）：

| 路径 | 说明 |
|------|------|
| `CLAUDE.md` | 启动入口 |
| `AGENTS.md` | 本文件 |
| `openspec/` | 规范与变更 |
| `.claude/` | 项目级配置与 hooks |
| `scripts/` | 构建/测试/harness 脚本 |
| `harness/` | Agent 工作流与上下文包 |

## OpenSpec 本地工作策略

- `openspec/specs/` 是项目长期真相（current behavior）。
- `openspec/changes/**` 是本地变更提案，跟随分支走，不合并到主干即视为本地。
- 所有功能工作默认从 `/change <需求路径>` 启动，在本地创建 `openspec/changes/<change-id>/`。
- 变更按 `openspec/changes/<change-id>/tasks.md` 逐条实现。
- 完成后将最终行为同步至 `openspec/specs/`，归档变更。

详细生命周期见 `harness/workflow/openspec-change-lifecycle.md`。

## 质量门

完成前必须运行：

```bash
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/harness/check_no_unfinished_markers.py
python3 scripts/harness/validate_task_files.py
```

有产品测试时一并运行 `./scripts/session-browser.sh test`。

### UI quality gates

对 `src/session_browser/web/templates/`、`src/session_browser/web/static/*.css` 或 `src/session_browser/web/static/js/` 的修改，
必须运行：

```bash
python3 scripts/quality/run_quality_gate.py --target session-detail
```

除非 `.agent/quality/<change-id>/quality-gate-summary.json` 报告 `status: PASS`，否则 UI 任务未完成。

详见 `harness/quality/quality-gate-matrix.md`、`harness/quality/ui-layout-contract.md`。

## 生成物策略

以下类别不提交：

- 本地运行数据（logs、临时文件、SQLite index）
- 报告/覆盖率/基准测试输出（`reports/` 下非基线文件）
- 用户个人配置（`.claude/settings.local.json`、`.mcp.json`）
- 缓存、密钥、真实 session 数据

生成物仅在本地消费，不在主干中长期保留。

## 文件操作协议

1. **搜索优先**：用 `rg` 或 `rg --files` 定位目标，不盲目猜测路径。
2. **最小读取**：只读必要的行和文件；大文件用分页或片段抽取。
3. **Diff 先行**：编辑前用 `git diff --stat` 了解现状，再定位相关文件。
4. **精准编辑**：用 `Edit` 工具做局部替换，避免整文件覆写。
5. **测试闭环**：每次变更后运行相关测试，保留关键失败信息。

## 目录职责

| 目录 | 职责 |
|------|------|
| `src/session_browser/` | 应用源码 |
| `tests/` | 单元测试、静态 DOM/HTML 结构测试 |
| `scripts/` | 本地运行、测试、发布、harness 脚本 |
| `harness/` | Agent/自动化工作流与上下文包 |
| `.claude/` | Claude Code 项目级共享配置和 hooks |
| `.agent/` | Agent 任务账本和执行记录 |
| `docs/` | 开发规范和项目文档 |

## 完成定义

1. 改动与用户目标直接对应。
2. 必要测试或质量门已运行，并在汇报中说明结果。
3. 文档、脚本、harness 与代码保持同步。
4. 没有提交个人配置、缓存、运行数据或生成物。
5. `git status --short` 无意外文件被纳入。

## 语言策略

- **默认输出简体中文**。
- 代码、命令、路径、API 名称保持英文原样。
- 面向用户的 UI 文本使用中文。

## prompts/ 目录策略

`prompts/` 目录是 **输入定义，非权威入口**。

- **不直接读取或执行** `prompts/` 下的文件（不通过 `Read prompts/...` 启动工作流）。
- 所有基于 prompt pack 的工作必须通过 `/change prompts/<path>` 启动，确保变更进入 OpenSpec 流程。
- 不删除当前 prompt packs，除非已确认废弃。

## Agent 规则

1. 从 `openspec/specs/` 获取当前真相。
2. 每个非平凡变更使用 `openspec/changes/<change-id>/`。
3. 保持任务文件小巧、串行、可独立验证。
4. 绝不覆盖用户本地设置。
5. 除非变更明确要求，否则保留现有产品代码。
6. 汇报完成前先验证质量门。
