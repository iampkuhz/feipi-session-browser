# 最小 Agent 运行契约

Claude Code 与 Codex 使用客户端已经选择的 checkout。仓库不为普通读取、编辑或提交维护
Session 状态，也不要求平台事件先完成初始化。机器契约见
`harness/agent-runtime.manifest.yaml`；Gate 机器真相集中在 `scripts/gates/catalog/`，人类手册位于
[`docs/gates/gate-control-plane.md`](../docs/gates/gate-control-plane.md)。自动增量规划由 changed path 直接匹配每个 Gate
的 Trigger；TargetPreset 只是人工选择的 Gate 分组，不参与自动规划。

## 生命周期与 Git 边界

- Session 的启动、恢复和结束由客户端负责；仓库配置不绑定平台事件矩阵。
- Agent 在当前 checkout 和当前分支中工作，不因仓库侧运行状态缺失而创建额外 worktree 或阻断写入。
- commit 是完成验证后的显式 Git 操作，只作用于当前分支和精确文件范围。
- 合并、发布及 primary 分支前进必须由用户后续明确选择；禁止 stash、reset、rebase、force 和未授权 push。
- 不读取或提交真实 session、密钥、token、缓存、运行数据或个人配置。
- 共享 checkout 的任务身份、并发数、Run 结束和 active-change 登记均不授予目录独占权。修复前区分本任务与继承差异，交付前核对其他聊天/进程的实际写入；操作与证据边界见[开发手册](development/README.md#共享-checkout-的实际写入边界)。不新增写入状态机或锁，不覆盖他人差异。

## OpenSpec 与策略

非平凡产品、agent、harness、gate、hook 或跨模块变更先创建或复用
`openspec/changes/<change-id>/`，再按 `tasks.md` 推进。OpenSpec 是规划和长期规格流程，不是每次文件
写入的状态令牌。普通定位和单文件小改只读取必要上下文。

策略约束来自 `AGENTS.md`、`.claude/CLAUDE.md`、`harness/agent-policy.manifest.yaml` 和共享 skills。平台配置只保留
入口、agent 发现和静态安全限制，不承担仓库状态协调。

## 原生 subagent 委派

普通小改由主线程处理；需要委派时使用当前 Agent 的原生 subagents。共享真源是
`harness/agent-policy.manifest.yaml` 的 `native_delegation` 与 `subagent_instance_protocol`。
不新增 CLI、调度器、队列、receipt、callback、watchdog、ack 或仓库任务状态机。

委派前必须读取共享 [subagent contract](../skills/authoring/feipi-openspec-orchestrate-change/references/subagent-contract.md)，
按 manifest 中的字段、模型路由、身份隔离和结果语义执行。客户端只保留读取入口，不复制协议正文；
修改交接要求时维护共享契约和 manifest，再运行 `agent.documentation` 检查及对应回归，不逐个平台改副本。

Qoder 工程派发已退役：旧 Qoder PASS 不能充当原生验收证据；旧 callback 到来仅识别为已退役，
不恢复或重新执行旧链。产品 Qoder session 的发现、解析、展示及导出仍受支持；通用安全保护不删除。
仅删除 tracked 工程入口，`/.qoder/` 个人配置和运行数据保持 ignored，不递归清理目录。

## 显式验证

日常反馈见[开发手册](development/README.md#日常小改)，提交或交接以 `AGENTS.md` 的完整工作区 Gate 为准。
`NOT_TRIGGERED` 表示未选择，不是执行结果；`BLOCKED` 表示发现阻断问题，`FAIL` 表示未完成。

修复循环与停止规则以共享[分层反馈闭环](../skills/authoring/feipi-quality-gate-diagnosis/references/repair-loop.md)为准。
Run completed 不是 Issue 验收通过；平台 max_attempts 不限制内部代码修复轮次。顺序启动也不是依赖验收，默认不绕过未验收的前置任务；用户明确授权前一 Run 终态后继续时可按该有界范围推进，但保留前项未解决责任，不宣称验收通过或取得目录锁。仓库约定不等于平台提供硬依赖锁。

## Multica 临时规则

仓库维护的 `AGENTS.md` 仍受 policy 的 2800-byte 限制。仅完整 Multica 任务环境、合法 UUID 身份及原生标记包裹的单个尾块，才按 `multica_runtime_bytes` 单独计费；HEAD/index 中不得存在该块，未知、损坏或持久化的标记均拒绝。
这只是临时格式和任务环境的一致性校验，不是对环境变量的密码学认证，也不能把产品缺陷归为平台重试。
Codex 的 `project_doc_max_bytes` 是完整物理指令的加载容量（含临时尾块），不是放宽源码上限。完整文件加安全余量必须能加载；不把尾块写入版本控制，不读取或打印 token，不改动个人配置或原生 Multica 注入器。
