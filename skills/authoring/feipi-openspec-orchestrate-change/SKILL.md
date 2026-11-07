---
name: feipi-openspec-orchestrate-change
disable-model-invocation: true
description: 为非平凡产品、跨模块或共享工程契约变更创建或复用 OpenSpec，推进实现和显式验证；不用于普通局部小改或只读查询。
---

# OpenSpec 变更编排

1. 在客户端选择的 checkout 搜索匹配 change 和相关长期 spec，只读与本任务有关的片段。`prompts/` 是请求来源，不是流程权威。
2. 用 `python3 scripts/openspec/create_active_change.py --change-id <id> --source <source>` 创建或复用；需要身份隔离时传入客户端、session 和 agent 参数。保留简短的 `proposal.md`（问题、范围、决策及风险）、`tasks.md`（实际任务与验收）和受影响的 `specs/<capability>/spec.md`。复杂设计才另写 `design.md`，不复制 proposal。模板按需取用，不要求每阶段另写报告。
3. 按任务修改，开发反馈用最邻近的原生检查；根据真实证据更新任务状态，不把同一检查每阶段重跑。需要委派才读 [共享 handoff](references/subagent-contract.md) 和 manifest；重要实现、复杂判断和独立复核按共享策略路由。主线程负责交付验证。
4. 交付前对最终 change 运行 `python3 scripts/openspec/validate_active_change.py --change-id <id>`；布局由增量 Gate 的 `governanceLayoutValidation` 承接，未触发才单独运行 `python3 scripts/openspec/validate_layout.py`。按 [AGENTS.md](../../../AGENTS.md) 对完整待验工作区运行 Gate，检查精确 diff 和安全边界。已被交付检查覆盖的产品测试不重复运行。
5. 仅在用户明确授权时 stage 精确范围并在当前分支 commit，不提交 ignored change、不自动集成或 push。报告变更、实测效果、验证、未覆盖项和提交（如有），未完成的 required checks 不算 PASS。
