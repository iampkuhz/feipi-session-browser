---
name: feipi-openspec-orchestrate-change
disable-model-invocation: true
description: 用于本仓库非平凡变更的 OpenSpec 生命周期编排：创建或复用 change，生成 proposal/design/tasks/spec，按任务推进实现，并显式验证、在当前分支提交。普通单文件修改或只读查询不要使用。
---

# OpenSpec 变更编排

本 skill 是仓库共享真源，用于编排非平凡变更的接收、检查、提案、规划、实现、验证和分支内收口。
Claude Code、Codex 和 Qoder 的工具入口只引用本目录。

## 策略

- **`prompts/` 是输入，不是流程权威。** 始终以本 skill、`AGENTS.md` 和当前 change 的 `tasks.md` 为准。
- **OpenSpec-first。** 非平凡产品、agent、harness、gate、hook 或跨模块变更先创建或复用
  `openspec/changes/<change-id>/`；普通只读查询和单文件小改不扩大流程。
- **客户端拥有 checkout。** 在客户端已经选择的 checkout 和分支中工作；仓库状态不是普通写入的授权令牌。
- **验证与提交均为显式步骤。** 先运行计划中的定向检查和唯一 required gate；成功后只 stage 精确归属路径，
  使用普通 `git commit` 在当前分支形成 commit。用户明确要求保留未提交状态时不提交。
- **集成由用户控制。** 不推进其他 checkout 或 primary 分支，不执行 stash、reset、force、rebase、
  cherry-pick、未授权 push 或远端 PR/MR。
- **结果语义真实。** required 检查 failed、warning、skipped、not-run 或 unavailable 时不得返回 PASS。

## 阶段 0：接收

1. 将用户文本或指定文件内容作为请求。
2. 派生短小的 `<change-id>`（kebab-case），并检查 `openspec/changes/` 是否已有匹配 change。
3. 读取 `AGENTS.md`、`openspec/config.yaml` 和请求直接相关的长期 spec；不展开无关 change 或真实运行数据。

## 阶段 1：创建或复用

1. 若 change 不存在，创建 `openspec/changes/<change-id>/`。
2. 写入 `tmp/active_change.json`，记录 `change_id`、`change_path`、来源、受保护范围和计划的 required gates。
3. 复用 change 时确认请求仍在 proposal/design/tasks 的边界内；不匹配则先修订计划。

## 阶段 2：检查

1. 先读当前任务对应的 proposal、design、tasks 和 delta spec。
2. 只读取与请求相关的源码、测试和配置片段。
3. 搜索现有实现与调用者，确认精确修改范围、隐私边界和验证入口。
4. 运行 OpenSpec layout validator，先消除结构问题。

## 阶段 3：提案

1. 写 `proposal.md`：问题、范围、非目标、用户影响、验证策略。
2. 写 `design.md`：当前状态、方案、风险、回滚、验证。
3. 写 `tasks.md`：顺序、小型、带验证的任务。
4. 在 `specs/` 写符合 schema 的增量规格。
5. 使用 `templates/` 中对应模板作为起点。

## 阶段 4：规划验证

依次运行：

```bash
python3 scripts/openspec/validate_layout.py
python3 scripts/openspec/validate_schema.py
python3 scripts/openspec/validate_active_change.py --change-id <change-id>
```

若变更影响 harness，再运行 `python3 scripts/harness/validate_harness_structure.py`。任何失败都先修复计划；
未运行的检查不得记录为通过。

## 阶段 5：实现

从上到下遍历 `tasks.md`：

1. 执行一个任务且不扩大范围。
2. 运行该任务声明的最小 deterministic validation。
3. 成功后勾选复选框并记录简短证据；失败时保留未完成状态。
4. 大型或边界清晰的工作可委派 subagent。handoff 必须引用 `tmp/active_change.json`、限定写范围和验证命令，
   并要求返回 `PASS`、`FAIL` 或 `BLOCKED`；详见 `references/subagent-contract.md`。
5. subagent 的 `FAIL` 或 `BLOCKED` 不得被主 agent 静默忽略。

## 阶段 6：验证

1. 运行 change 中列出的全部定向验证。
2. 重新运行 OpenSpec layout、schema 和 active-change validators。
3. 产品代码或测试变更运行 `./scripts/session-browser.sh test`；其他 target 按 gate catalog 触发。
4. 提交或交接前显式运行：

   ```bash
   python3 scripts/gates/cli.py --tier required
   ```

5. required gate 只有所有已触发检查成功且无 warning、skipped 时才算通过。

## 阶段 7：当前分支收口与汇报

1. 用 `git status --short`、`git diff --check` 和精确 changed-files 清单确认没有真实 session、密钥、token、
   缓存、个人配置、越界文件或他人并行修改。
2. required gate 成功后，若用户未要求保留未提交状态，使用 `git add -- <exact-owned-paths>`，检查
   `git diff --cached --check` 和 staged 清单，再执行普通 `git commit -m '<type(scope): summary>'`。
3. commit 保留在当前分支；不合并其他 checkout，不推进 primary，不 push。
4. 输出：精确 changed files、每条 validation 的真实结果、Effect checks、当前分支 commit（如有）和 Risks。
   最终状态固定为 `PASS`、`FAIL` 或 `BLOCKED`。

## 参考

- 简版流程：`references/workflow.md`
- 子代理继承契约：`references/subagent-contract.md`
- 模板：`templates/`
