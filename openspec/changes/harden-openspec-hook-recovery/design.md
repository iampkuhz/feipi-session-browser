# 设计：harden-openspec-hook-recovery

## 当前状态

`scripts/openspec/create_active_change.py` 创建 change 文件时是幂等的，但对 `.agent/active_change.json` 使用 `setdefault` 合并策略。已有 sentinel 指向旧 change 时，新 change 不会成为 active change。

`scripts/agent_hooks/guard_active_openspec_change.py` 只验证 active change 目录存在，不验证 `proposal.md`、`design.md`、`tasks.md`。因此空目录也能放行受保护文件编辑。

`.claude/hooks/stop_check.sh` 将 Stop 验证失败汇总为 `EXIT_WARN=1`。在 Claude Code 记录中这类失败可能表现为非阻塞 hook 错误，不能稳定转化为“继续修复”的模型上下文。

## 提议的方法

1. `create_active_change.py` 保持 change 文件幂等，但始终把 active sentinel 写成本次请求的 change。若 sentinel 原先指向其他 change，CLI 输出 `Updated active change`。
2. `guard_active_openspec_change.py` 在受保护编辑前要求 active change 目录包含 `proposal.md`、`design.md`、`tasks.md`。写入 `openspec/changes/` 和 `.agent/active_change.json` 仍作为创建阶段例外。
3. `stop_validate_change.py` 对不完整状态返回阻塞退出码 `2`，并输出明确的继续步骤：修复 active sentinel、补齐文件、保留 evidence、标记 task。
4. `stop_check.sh` 区分 warning 和 blocking。普通本地文件提示仍返回 warning；OpenSpec/质量门失败返回 `EXIT_BLOCK=2`。

### 关键决策

1. active sentinel 必须可切换。
   “active” 的语义是当前工作上下文，而不是第一次创建后永久固定。

2. 阻塞尽量前移。
   不完整 change 应在受保护编辑前被发现，Stop 阶段只负责最终兜底。

3. Stop 输出必须面向 LLM 操作。
   只列出错误不足以恢复流程，必须给出下一步动作。

## 风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 旧脚本调用方依赖“不切换 active change” | 低 | 中 | active change 的命名语义本身要求切换；change 文件仍幂等不覆盖 |
| 创建 change 初期被 PreToolUse 阻止 | 低 | 中 | `openspec/changes/` 与 `.agent/active_change.json` 保留创建例外 |
| Stop 阻塞影响临时暂停 | 中 | 低 | 保留 `FEIPI_SKIP_STOP_HOOK=1` 紧急绕过 |

## 回滚

回滚本变更提交即可恢复旧 hook 行为。不会产生数据库迁移或产品数据变更。

## 验证

- [ ] `python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test`
- [ ] `python3 scripts/agent_hooks/stop_validate_change.py --self-test`
- [ ] harness/OpenSpec 结构质量门
