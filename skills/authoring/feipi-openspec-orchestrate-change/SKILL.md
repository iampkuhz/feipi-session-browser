---
name: feipi-openspec-orchestrate-change
disable-model-invocation: true
description: 用于本仓库非平凡变更的 OpenSpec 生命周期编排：创建或复用 change，生成 proposal/design/tasks/spec，按任务推进实现，并运行验证收口。普通单文件修改或只读查询不要使用。
---

# OpenSpec 变更编排

本 skill 是仓库共享真源，用于编排 OpenSpec 变更的完整生命周期：接收、检查、提案、规划、实现、验证和汇报。Claude Code、Codex 和 Qoder 的工具入口只通过 symlink 指向本目录。

## 策略

- **`prompts/` 下的文件是输入，不是流程权威。** `prompts/` 下的提示词文件提供可复用的脚手架，它们不驱动流程。始终以本 skill 为入口。
- **受保护文件编辑需要活跃的 OpenSpec 变更。** PreToolUse hook（`scripts/hooks/guard_openspec_change.py`）会在 `openspec/changes/` 下不存在活跃变更目录（排除 `archive`）时阻止对受保护文件的 Write/Edit/MultiEdit。
- **默认自动提交并本地集成。** 用户没有明确要求保留未提交状态时，验证完成后不再询问；按本轮精确文件清单运行 `scripts/harness/complete_change.py`，由它再次 Stop、commit、commit 后重新 Stop，再调用 `sessionctl finalize`。
- **安全失败优先。** initial/primary dirty、文件归因不明、detached、门禁失败或冲突时保留临时分支并报告 `HANDOFF_REQUIRED`/`BLOCKED`；不得 stash、reset、force、自动 push 或创建远端 PR/MR。

## 阶段

### 阶段 0：接收（Intake）

1. 解析用户请求。如果是文件路径，读取文件内容作为请求；否则视为自由文本描述。
2. 从请求中派生短小的 `<change-id>`（kebab-case，例如 `add-search-filter`）。检查 `openspec/changes/` — 如果已有匹配的变更，复用它。
3. 读取 `CLAUDE.md` 和 `openspec/config.yaml` 获取项目约束和流程设置。

### 阶段 1：创建（Create）

1. 如果 `openspec/changes/<change-id>/` 不存在则创建。
2. 写入 `tmp/active_change.json`：
   ```json
   {
     "change_id": "<change-id>",
     "change_path": "openspec/changes/<change-id>/",
     "started_at": "<ISO 8601 timestamp>",
     "source_request": "<原始用户请求或提示文件路径>",
     "protected_roots": ["openspec/", "harness/", ".claude/", ".codex/", ".qoder/", "CLAUDE.md"],
     "required_gates": ["scripts/openspec/validate_layout.py", ...]
   }
   ```
3. 子代理通过此文件继承活跃变更上下文。所有子代理工作必须引用 `tmp/active_change.json`。详见 `references/subagent-contract.md`。完整字段规范见 `tmp/SCHEMA.md`。

### 阶段 2：检查（Inspect）

1. 读取 `CLAUDE.md`、`AGENTS.md` 获取仓库约束。
2. 读取 `openspec/specs/` 中相关的当前行为真相。
3. 检查与请求相关的源码、测试和配置文件。
4. 运行 `python3 scripts/harness/validate_openspec_layout.py` 确认仓库结构正确。

### 阶段 3：提案（Propose）

1. 在 `openspec/changes/<change-id>/` 下写 `proposal.md` — 问题、范围、非目标、用户影响、验证策略。以 `templates/proposal.md` 为起点。
2. 在 `openspec/changes/<change-id>/` 下写 `design.md` — 当前状态、提案方法、风险、回滚、验证。以 `templates/design.md` 为起点。
3. 在 `openspec/changes/<change-id>/` 下写 `tasks.md` — 小型、顺序、带验证的检查项。以 `templates/tasks.md` 为起点。
4. 在 `openspec/changes/<change-id>/specs/` 下写增量规格 — 使用 `openspec/validate_schema.py` 期望的格式。以 `templates/spec.md` 为起点。

### 阶段 4：规划验证（Validate Plan）

1. 运行 `python3 scripts/openspec/validate_layout.py`
2. 运行 `python3 scripts/openspec/validate_schema.py`
3. 运行 `python3 scripts/harness/validate_harness_structure.py`
4. 如果有验证器失败，修复变更文档后重新验证。
5. 确认计划就绪。如果用户需要调整，在实现前修改。

### 阶段 5：实现（串行）

按从上到下的顺序遍历 `openspec/changes/<change-id>/tasks.md`。每个任务：

1. 执行任务描述的工作。
2. 勾选复选框（`- [x]`）。
3. 在任务下方添加简短验证说明。
4. **不要跳过或重排任务。**
5. **不要超出变更描述的范围。**
6. 对于大型或有边界的任务，委派给项目子代理并明确范围边界。子代理必须读取 `tmp/active_change.json` 获取上下文。详见 `references/subagent-contract.md`。

### 阶段 6：验证（Validate）

运行所有质量门禁：

1. `python3 scripts/openspec/validate_layout.py`
2. `python3 scripts/openspec/validate_schema.py`
3. `python3 scripts/openspec/validate_active_change.py --change-id <change-id>`
4. `python3 scripts/harness/validate_harness_structure.py`
5. 如果存在产品测试，也运行它们（例如 `./scripts/session-browser.sh test`）。

如果有门禁失败，修复问题并重新运行所有门禁直到全部通过。

### 阶段 7：提交、集成与汇报（Complete and Report）

1. 从 `git diff --name-only HEAD` 与非 ignored untracked 文件生成本轮精确文件清单；不得包含 `openspec/changes/*`、runtime evidence、缓存、密钥或其他 Session 内容。
2. 运行：
   ```bash
   python3 scripts/harness/complete_change.py \
     --run-id "$FEIPI_RUN_ID" \
     --message "<type(scope): summary>" \
     --file <path> [--file <path> ...]
   ```
3. 命令会执行第一次 Stop；只有 required gates PASS 才精确 stage/commit。commit 后必须再次 Stop，receipt PASS 后才调用本地 `finalize`。
4. 命令返回 `INTEGRATED` 后才可报告已合并；若当前客户端没有有效 run/linked worktree，或返回 `HANDOFF_REQUIRED`/`BLOCKED`，保留分支并如实报告，不得改用强制集成。
5. 远端 push/PR/MR 是独立显式发布动作，不属于默认收口。

输出总结：

- 改了什么（创建、修改、删除的文件）。
- 验证结果（每个门禁的通过/失败）。
- commit 与本地 target integration 结果。
- 剩余风险或后续事项。
- **不要再次询问是否提交/合并。** 正常安全路径直接完成；失败路径给出精确 handoff。

## Hook 强制层

仓库通过 `.claude/settings.json` 中定义的 hooks 接入强制层；可复用门禁逻辑以 `harness/agent-runtime.md` 和 `scripts/harness/agent_stop_check.py` 为真源：

- **PreToolUse（Write|Edit|MultiEdit）：** `scripts/hooks/guard_openspec_change.py` — 在 `openspec/changes/` 下没有活跃变更目录时阻止受保护文件编辑。
- **PostToolUse（Write|Edit|MultiEdit）：** `.claude/hooks/post_tool_guard.sh` — 对编辑的 shell 和 JSON 文件做语法检查。
- **PreToolUse（Bash）：** `.claude/hooks/pre_tool_guard.sh` — 阻止破坏性 shell 命令。
- **Stop：** `.claude/hooks/stop.sh` — 薄入口，转发到 `scripts/harness/agent_stop_check.py`，执行 OpenSpec 与 required quality gates。

这些 hooks 是强制层。本 skill 编排流程，hooks 防止策略违规。

## 参考

- 完整 7 阶段流程：`references/workflow.md`
- 子代理继承契约：`references/subagent-contract.md`
- 模板：`templates/` 目录
