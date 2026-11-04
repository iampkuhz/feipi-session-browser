# Native Subagent Delegation Spec

## Requirements

### Requirement: 当前 Agent 原生委派

工程任务 SHALL 直接使用当前 Agent 提供的原生 subagent 能力。主线程 SHALL 负责目标拆分、范围、独立复核与集成。重要实现、复杂分析及验证 SHALL 使用 `gpt-6.1-sol`，轻量定位 SHALL 使用 `gpt-6-luna`；调用 SHALL 遵守宿主原生 API 的模型与上下文约束。原生能力受限时 SHALL 如实说明，由主线程接管或调整范围，不新增替代调度框架。工程任务 SHALL NOT 要求 Qoder CLI 或工程 `.qoder/` 开发入口。

#### Scenario: 实现与轻量定位

- **Given** 当前 Agent 能直接派发原生 subagent
- **When** 主线程拆分重要实现及轻量定位任务
- **Then** 分别使用 `gpt-6.1-sol` 和 `gpt-6-luna`，显式传递必要上下文，使用宿主原生生命周期
- **And** 不调用 qodercli、不启动仓库 worker/callback/watchdog、不要求新 receipt

### Requirement: 复用共享 handoff 与证据隔离

每个原生子任务 SHALL 包含 Goal、Task id、Task source、Allowed files/directories、Forbidden files/directories、Required context files、Expected output、Validation command、Failure policy。每实例 SHALL 有唯一 Task id/agent_id 或等价身份；修改型任务 SHALL 使用不重叠写范围，不回滚他人修改。结果 SHALL 包含 Status、Changed files、Validation、Effect checks、Risks，Status SHALL 为 PASS、FAIL 或 BLOCKED。主线程 SHALL 仅聚合同 client/session_id 的证据；FAIL/BLOCKED SHALL 被处理而非静默跳过。

#### Scenario: 两个修改型子任务

- **Given** 两个任务共享当前 checkout
- **When** 主线程派发并接收结果
- **Then** handoff 标明互斥写范围、必要上下文及独立身份，结果归属当前 client/session
- **And** 主线程串行集成，独立运行交付 required checks，不把子任务 PASS 当作整体验收

### Requirement: 权限和验证真实性保持

原生委派 SHALL 保持当前环境权限，不继承工程 Qoder 的 `bypass_permissions` 默认值，也不得失败后自动升级权限。主线程 SHALL 保留隐私、密钥、真实 session、ignored 数据、skip/warning、OpenSpec、构建与产品测试保障。required checks 出现失败、skipped、warning、not-run 或 unavailable 时 SHALL NOT 宣称交付 PASS。

#### Scenario: 原生任务验证不完整

- **Given** 子任务完成修改但 required check 尚未运行或出现 skipped
- **When** 主线程汇总结果
- **Then** 明确报告未完成/失败范围，不通过删除正向断言、降低检查或提高权限使结果变绿

### Requirement: Qoder 专属工程调度契约退役

`openspec/specs/qoder-subtask-cli/spec.md` 的工程要求 SHALL 退役，包含 Qoder 默认实现、CLI start/resume/status/result、独立 run、父回调、watchdog、ack、supersession、Qoder 权限模式与派发详情卡。对应脚本、专属测试、文档和活跃命令登记 SHALL 移除，SHALL NOT 以新 CLI、队列、callback、watchdog、receipt 或仓库状态机重新实现。

旧 Qoder PASS SHALL NOT 作为原生验收证据；旧 callback 若到来 SHALL 仅识别为已退役，SHALL NOT 恢复或重新执行旧链。

#### Scenario: 旧入口重新出现

- **Given** 工程已改为当前 Agent 原生委派
- **When** 变更重新添加旧公开 Qoder 派发命令、默认 Qoder policy 或 tracked 工程入口
- **Then** 定向退役回归 SHALL 检出这一变化，不把旧链当作有效 fallback

### Requirement: 工程平台登记与产品支持分离

`agent-harness`、`agent-session-runtime`、`repository-root-layout` 及 runtime/skill/agent manifests SHALL 不再把 `.qoder/` 作为受维护的工程客户端入口或 parity 要求。删除 SHALL 仅限 Git 跟踪的工程文件/符号链接；整个 `/.qoder/` SHALL 保持 ignored，本地个人配置与运行数据 SHALL NOT 被删除。通用 credential guard 和高风险路径保护 MAY 保留对 `.qoder/` 的覆盖。产品 Qoder session 发现、解析、展示及导出能力 SHALL 保持，不属于本次退役范围。

#### Scenario: 退役时存在个人配置

- **Given** `.qoder/` 同时包含 tracked 工程入口和 ignored 本地文件
- **When** 移除工程平台与入口
- **Then** 只删除 tracked 工程入口，不递归清理目录，不纳入本地文件，不删除安全防护
- **And** 产品 Qoder session 能力及对应产品回归继续有效
