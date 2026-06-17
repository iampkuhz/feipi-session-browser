# 变更生命周期

仅当任务属于非平凡变更、OpenSpec、harness、质量门、hooks、agent 配置或流程调整时读取本文件。

## 基本流程

1. 确认是否已有匹配的 `openspec/changes/<change-id>/`。
2. 若没有，先补齐 `proposal.md` 和 `tasks.md`；需要设计权衡时补 `design.md`。
3. 按 `tasks.md` 串行推进实现，不绕过 OpenSpec 大改受保护路径。
4. 每完成一个任务，运行任务指定的最小验证。
5. 结束前运行本次触发的 required quality gate baseline。
6. 行为稳定后，同步长期规格到 `openspec/specs/`，再归档本地变更。

## 本地变更状态

- `openspec/changes/*` 默认是本地工作态，除非用户明确要求，不强制加入提交。
- `openspec/specs/` 表示长期行为真相，不能与代码、脚本和测试明显冲突。
- `tmp/active_change.json` 或 `openspec/active_change.json` 只能作为运行态提示，不替代规格和任务文件。

## 受保护路径

修改以下路径时必须说明任务目标并保持最小 diff：

- `.claude/`、`.codex/`、`.qoder/`、`.agents/`、`skills/`
- `openspec/`、`harness/`、`scripts/`
- `src/session_browser/`、`tests/`
- `AGENTS.md`、`CLAUDE.md`

## 完成要求

- required gate 失败即阻断，不得描述为通过。
- 生成物、缓存、真实 session data、密钥、token 和个人配置不得提交。
- 若环境导致验证无法运行，输出阻断原因和可复现命令。
