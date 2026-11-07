# Agent Harness Spec

## Requirements

### Requirement: OpenSpec 用于非平凡变更规划

仓库 SHALL 在跨模块产品、agent、harness、gate、hook 或规则变更前创建或复用 OpenSpec change；普通只读查询和单文件小改 SHALL NOT 因缺少 active change 被本地 Hook 阻断。

#### Scenario: 非平凡仓库变更

- **Given** 请求会改变多个模块或长期工程契约
- **When** Agent 开始实现
- **Then** Agent SHALL 先创建或复用 OpenSpec change
- **And** 规划义务 SHALL 由仓库规则和评审承担，而不是由 Session 状态授权写入

### Requirement: 非侵入式本地 Harness

本地 Harness SHALL 保持轻量且显式，不得要求 Registry、runId、writer lease、baseline、fencing token 或 Hook receipt 才允许普通 mutation。

#### Scenario: 客户端已选择 checkout

- **Given** Claude 或 Codex 已在一个 checkout 中工作
- **When** Agent 读取、编辑或运行本地命令
- **Then** 仓库 SHALL NOT 因缺少 Session runtime 状态阻断操作
- **And** checkout、分支和 worktree 生命周期 SHALL 由客户端与显式 Git 操作管理

### Requirement: 禁止自动 Git mutation

Stop、SessionEnd、post-tool 或其他自动事件 SHALL NOT stage、commit、merge、rebase、reset、stash、force 或 push 用户分支。

#### Scenario: 任务结束时存在修改

- **Given** 当前分支包含已验证或待验证修改
- **When** Agent 停止或 Session 结束
- **Then** 修改 SHALL 保留在当前分支
- **And** commit、integration 与发布 SHALL 只在明确任务或用户授权下执行

### Requirement: 显式且按范围的质量验证

仓库 SHALL 通过 `python3 scripts/gates/cli.py` 提供统一 Gate 入口。普通局部变更 SHALL 用最邻近的原生检查获得反馈，不强制 OpenSpec、委派或先跑整套 Gate。内部命名和非 Java 维护文字的语言偏好由评审处理，不作为启发式门禁；版本契约及现有 Java、隐私、安全和测试规则 SHALL 保留。

#### Scenario: 当前 checkout 准备提交或交接

- **Given** checkout 有待交付差异
- **When** Agent 准备提交或交接
- **Then** Agent SHALL 显式运行 `python3 scripts/gates/cli.py run --mode incremental`，由默认 Git 快照对整个待交付工作区按 Trigger 选择检查
- **And** 局部反馈、人工路径或旧 receipt SHALL NOT 替代交付验证，工具复用 SHALL 与实际测试执行区分
- **And** 完整的根 `check` 已承接全模块测试与零跳过时，不重复执行相同产品测试

### Requirement: 真实验证状态

Gate 终态 SHALL 为 `PASS`、`BLOCKED` 或 `FAIL`：`BLOCKED` 表示检查已完整执行并发现阻断问题，
`FAIL` 表示 Gate 自身未能完成、无法判断仓库。两者均不得描述为 PASS。

#### Scenario: Gate 未被路径映射触发

- **Given** changed-files 规则没有选择某 Gate
- **When** 生成验证报告
- **Then** 计划 SHALL 将该 Gate 标记为 `NOT_TRIGGERED`
- **And** 报告 SHALL NOT 将它当作 Gate 执行结果或 PASS 证据

#### Scenario: 已触发测试发生 skip 或 warning

- **Given** pytest、Playwright、Gradle 或 doctor 已被选择运行
- **When** 结果包含 skipped 或 warning
- **Then** 验证 SHALL 返回 FAIL
- **And** Agent SHALL 修复原因或移除错误触发，不得新增 skip、skipif 或 fixme API

### Requirement: 保留高价值安全检查

Harness 精简 SHALL 保留密钥、真实 session、隐私数据、ignored/generated path、测试 skip/warning、OpenSpec 结构和产品构建测试；不得通过降低阈值或删除产品 contract 换取通过。

#### Scenario: 删除旧 Runtime 检查

- **Given** Hook/Session Runtime 已无生产入口
- **When** 删除对应代码和低价值测试
- **Then** 仅验证旧文件存在、私有 helper 或平台 Hook parity 的检查 MAY 被删除
- **And** 产品、隐私和验证真实性检查 SHALL 保留

### Requirement: 确定性的 Python 与 Gate 执行环境

Gate SHALL 使用仓库锁定依赖可用的 Python 环境，并保留 bounded subprocess、资源锁、稳定报告和内容敏感 changed-files 语义；这些通用能力不得依赖 Agent Session Runtime。

#### Scenario: 系统 Python 缺少开发依赖

- **Given** PATH 中的 `python3` 缺少 PyYAML 或 pytest
- **When** 运行 Gate
- **Then** Gate SHALL 选择仓库批准的项目 Python 或 `uv run --frozen`
- **And** 缺失能力 SHALL 返回带 reason code 的 FAIL，不得伪造 PASS

### Requirement: 复用当前 Agent 原生委派

工程子任务 SHALL 复用当前 Agent 原生 API 和共享 handoff 协议，模型路由 SHALL 以 `harness/agent-policy.manifest.yaml` 为真源；具体契约见 `native-subagent-delegation`。工程 SHALL NOT 依赖 Qoder CLI 或另建队列、callback、watchdog、receipt 和任务状态机。

#### Scenario: 主线程派发与集成

- **Given** 当前 Agent 提供原生 subagents
- **When** 主线程分配实现或独立验证任务
- **Then** handoff SHALL 限定必要上下文、唯一身份及互斥写范围
- **And** 主线程 SHALL 仅聚合同 client/session_id 证据，独立运行 required checks，不接受旧 Qoder PASS 替代验收
