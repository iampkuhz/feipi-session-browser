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

Gate SHALL 使用 Harness 选定的同一个 Python 解释器；开发依赖缺失时明确报错，不另找解释器。无 selector 的增量计划只按变更路径选择 Gate。增量输入 SHALL 只从 Git 当前工作区或显式 Git 基线采集，不接收人工路径清单。仓库边界检查 SHALL 检查全部跟踪路径，不提供 staged 子集。Playwright 使用原生发现和仓库受管的合成会话服务，不接收外部会话 URL。Scan smoke 由公开 launcher 准备所需产物，Gate 不预跑 Gradle。

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

### Requirement: 分层反馈与有效进展

修复 SHALL 先有失败/预期依据，再最小修复、原单点反馈、实际消费者回归和最终整个工作区增量 Gate。内部修复轮次 SHALL NOT 受平台 max_attempts 限制。有新修复或能改变下一动作的证据 SHALL 继续；仅同签名同输入连续无进展且安全替代方法耗尽，或确有外部依赖，才可说明阻塞。

#### Scenario: 低成本静态失败先于重测试反馈

- **Given** 改动涉及格式、Javadoc 或邻近静态规则
- **When** 选择本次开发反馈命令
- **Then** SHALL 先使用既有原生入口检查精确路径或所属模块/source set，失败先修复，再运行原失败单点和实际消费者回归
- **And** SHALL NOT 将 Java `test --tests` 当作源码质量检查，或将 Python `ruff check` 当作格式检查；不新增调度层，最终整个工作区 Gate 不变

#### Scenario: 最终回归发现新问题

- **Given** 单点与相关回归通过，但最终 Gate 未通过
- **When** Agent 核对失败步骤
- **Then** 按证据归组并返回最小复现，而不是仅因 Gate 失败结束任务
- **And** 不削弱断言或只以测试数下降判断进展

### Requirement: 临时注入不削弱文档政策

仓库 SHALL 保留维护规则体积限制；仅具有完整任务环境、原生标记且未进入 Git 的严格有界临时尾块可独立核验，Codex 预算 SHALL 覆盖完整文档。缺身份、持久化、异常边界及超限注入 SHALL 阻断；格式与环境一致性 SHALL NOT 被称为密码学认证。

#### Scenario: 临时注入与恢复

- **Given** 合成任务追加符合协议的临时规则
- **When** 文档检查运行
- **Then** 基础规则与临时块各自受限且完整可读
- **And** 删除任务身份、破坏边界或将尾块纳入 Git 都不能通过

#### Scenario: 原生尾块携带恢复边界元数据

- **Given** 完整任务环境下的原生尾块在首行携带 `original-boundary` 元数据
- **When** 文档检查拆分源码和临时块
- **Then** 仅接受值为转义换行序列的单行元数据，且其字节仍计入临时块预算
- **And** 重复、移位、空正文、任意内容和 Git 持久化标记仍须阻断，源码预算不变

### Requirement: 稳定输入与可诊断测试环境

输入漂移 SHALL 留下失效的 FAIL 凭证、先前结果和漂移路径，不发布通过。fixture SHALL 使用本 run 分发副本，并在页面测试前核对关键同源资源的状态和类型。

#### Scenario: 验证期间修改与资源故障

- **Given** 合成测试期间输入变化或静态 JS 返回 500
- **When** 验证结束或 fixture 就绪检查运行
- **Then** 记录输入失效或资源故障，而不是产品交互成功

#### Scenario: 重采样路径不可读取

- **Given** 最终重采样无法读取某个已知输入
- **When** 保存本次 receipt
- **Then** SHALL 保留 FAIL、原指纹/步骤结果及日志，`afterFingerprint` 为 null，`unavailablePaths` 记录已知仓库相对路径，不暴露原始私有异常详情
- **And** 不把不可读路径冒充已确认的 `changedPaths`，无具体路径的故障不猜路径

#### Scenario: 共享 checkout 的局部反馈与交付范围

- **Given** 同一 checkout 含继承差异，且其他聊天/进程也可能写入
- **When** 修复与交付
- **Then** SHALL 在修复前区分本任务写范围/继承差异，在最终验证前核对实际写入来源；任务身份、Run 结束和并发限制不是目录锁
- **And** 局部反馈只选本根因/消费者，不自动扫描全脏区；最终仍验证整个工作区，说明本 Run 改动、继承差异、有效证据与剩余责任
- **And** 资源故障先以共同日志/响应证据归组，不新增 lease/状态机，不要求用户逐小步登记

### Requirement: 依赖依据验收放行

Run 正常结束 SHALL NOT 当作前置任务已验收；前置 blocked、failed 或待验收默认 SHALL 阻止 Agent 自行进入后续产品修改。用户明确授权按前一 Run 终态继续时 SHALL 仅在授权范围推进并保留遗留责任，不宣称前项验收通过、目录独占或已有平台硬依赖锁。

#### Scenario: 队列中的后续任务已经启动

- **Given** 前置 Issue 仍 blocked 或待验收且无用户明确的继续授权
- **When** 宿主 Agent 开始后续依赖任务
- **Then** 核对实际验收状态与证据并安全结束，不进入产品修改

### Requirement: fixture JDK 一致性

fixture SHALL 复用共享 JDK 25 发现，保持单点反馈与 Gate 的运行条件一致。

#### Scenario: npm 单点与 Gate 使用同一 JDK

- **Given** 系统默认 Java 不是原生 JDK 25，且共享发现可找到有效 JDK 25
- **When** 直接通过 npm 启动合成 fixture
- **Then** fixture SHALL 在隔离 HOME 前调用共享发现，并将同一 JAVA_HOME/PATH 传给构建及 launcher
- **And** 显式无效 JAVA_HOME SHALL 失败，不回退系统 Java
