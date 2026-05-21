# OpenSpec 变更流程 — 7 阶段

本文档描述了 OpenSpec 变更的标准 7 阶段流程。它被 `change` skill 引用，提供每个阶段的详细指引。

## 概览

```
阶段 0：接收  →  阶段 1：创建  →  阶段 2：检查  →  阶段 3：提案
                                                                    ↓
阶段 7：汇报  ←  阶段 6：验证  ←  阶段 5：实现  ←  阶段 4：规划
```

每个阶段都有入口条件、步骤和出口条件。不要跳过任何阶段。

---

## 阶段 0：接收（Intake）

**入口：** 用户提供请求（自由文本或文件路径）。

**步骤：**

1. 解析请求。如果是文件路径，读取其内容。
2. 从请求派生 `<change-id>`（kebab-case）。
3. 检查 `openspec/changes/` 是否已有匹配的变更。
4. 读取 `CLAUDE.md` 和 `openspec/config.yaml` 获取约束。

**出口：** 明确的 `<change-id>` 和对项目约束的理解。

---

## 阶段 1：创建（Create）

**入口：** 来自接收阶段的有效 `<change-id>`。

**步骤：**

1. 如果 `openspec/changes/<change-id>/` 不存在，创建目录。
2. 写入 `tmp/active_change.json` 注册活跃变更：
   ```json
   {
     "change_id": "<change-id>",
     "change_path": "openspec/changes/<change-id>/",
     "started_at": "<ISO 8601 timestamp>",
     "source_request": "<原始用户请求或提示文件路径>",
     "protected_roots": ["openspec/", "harness/", ".claude/", "CLAUDE.md"],
     "required_gates": ["scripts/openspec/validate_layout.py", ...]
   }
   ```
   完整字段规范见 `tmp/SCHEMA.md`。

**出口：** 变更目录已创建，`tmp/active_change.json` 已写入。

---

## 阶段 2：检查（Inspect）

**入口：** 活跃变更已注册。

**步骤：**

1. 读取 `CLAUDE.md`、`AGENTS.md` 获取仓库约束。
2. 读取 `openspec/specs/` 中相关规格，了解当前行为。
3. 检查与变更相关的源码、测试和配置文件。
4. 运行 `python3 scripts/harness/validate_openspec_layout.py` 确认结构正确。

**出口：** 对当前状态和相关文件有清晰理解。

---

## 阶段 3：提案（Propose）

**入口：** 检查完成。

**步骤：**

1. 写 `proposal.md` — 问题、范围、非目标、用户影响、验证策略。
2. 写 `design.md` — 当前状态、提案方法、风险、回滚、验证。
3. 写 `tasks.md` — 带验证步骤的细粒度顺序任务。
4. 在 `openspec/changes/<change-id>/specs/` 下写规格增量。

**出口：** 所有提案文档和规格增量已写入。

---

## 阶段 4：规划（验证计划）

**入口：** 提案和规格增量已写入。

**步骤：**

1. 运行 `python3 scripts/openspec/validate_layout.py`
2. 运行 `python3 scripts/openspec/validate_schema.py`
3. 运行 `python3 scripts/harness/validate_harness_structure.py`
4. 修复任何验证失败。
5. 向用户展示计划等待批准。

**出口：** 所有验证器通过且用户批准计划。

---

## 阶段 5：实现（串行）

**入口：** 计划已批准。

**步骤：**

1. 从上到下遍历 `openspec/changes/<change-id>/tasks.md`。
2. 每个任务：
   - 执行工作。
   - 勾选复选框（`- [x]`）。
   - 添加验证说明。
3. 不要跳过或重排任务。
4. 不要超出变更描述的范围。
5. 对于大型任务，委派给子代理并明确范围（见 `subagent-contract.md`）。

**出口：** 所有任务完成并标记为已done。

---

## 阶段 6：验证（Validate）

**入口：** 所有实现任务已完成。

**步骤：**

1. 运行 `python3 scripts/openspec/validate_layout.py`
2. 运行 `python3 scripts/openspec/validate_schema.py`
3. 运行 `python3 scripts/openspec/validate_active_change.py --change-id <change-id>`
4. 运行 `python3 scripts/harness/validate_harness_structure.py`
5. 运行产品测试（如有）。
6. 修复任何失败项并重新运行直到全部通过。

**出口：** 所有质量门禁通过。

---

## 阶段 7：汇报（Report）

**入口：** 所有质量门禁通过。

**步骤：**

1. 总结变更内容（创建、修改、删除的文件）。
2. 汇报验证结果（每个门禁通过/失败）。
3. 注明剩余风险或后续事项。
4. 提交前询问用户。

**出口：** 用户收到汇报并决定是否提交。

---

## 变更后：归档（Archive）

变更已提交并批准后：

1. 将 `openspec/changes/<change-id>/specs/` 中的规格增量合并到 `openspec/specs/`。
2. 将变更目录移至 `openspec/changes/archive/<change-id>/`。
3. 删除 `tmp/active_change.json` 或更新为下一个活跃变更。

这由 `openspec/config.yaml` 中的 `final_specs_update_rule` 管控。
