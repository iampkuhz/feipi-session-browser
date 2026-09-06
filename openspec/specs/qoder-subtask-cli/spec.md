# Qoder Subtask CLI

## Status
ADDED

## Requirements

### Requirement: 显式低开销委派
脚本 SHALL 显式启动带完整 handoff 与独立身份的 qodercli 子任务，立即返回唯一 run id（UUID）。SHALL NOT 持续轮询、无限续跑或自动进行 Git mutation；用户已明确授权默认 bypass_permissions。

#### Scenario: 后台执行
- **Given** 有效任务输入和可运行 qodercli
- **When** 调用 `start`
- **Then** 立即返回 UUID run id，worker 后台阻塞等待退出并原子保存完成记录；`status`/`result` 单次读取。

### Requirement: 精确恢复与真实结果
`resume` SHALL 只恢复记录中的 Qoder session id（使用 `--resume <saved UUID>`，不使用 `--continue` 或 `--session-id`）。进程退出 0 SHALL NOT 自动等价于质量验收 PASS（标记为 `finished` 而非 `PASS`）。主线程 SHALL 保持 Qoder 来源身份，独立复核，不混用其他 client/session 证据。

#### Scenario: 失败或缺失
- **Given** CLI 缺失、非法路径、非零退出或尚无完成记录
- **When** 查询或启动任务
- **Then** 明确失败或未完成，不伪造 PASS，不自动扩大权限或读取其他任务。

### Requirement: 输入校验与注入防护
任务输入 SHALL 为包含完整九项 handoff 的 JSON。参数 SHALL 以数组传递（无 `shell=True`/`eval`）。Run ID SHALL 使用 UUID 格式。`permission_mode` SHALL 仅接受 `default`/`accept_edits`/`dont_ask`/`bypass_permissions`。用户明确授权下缺省 SHALL 为 `bypass_permissions`，SHALL 持久化有效模式并仅传 `--permission-mode`，不叠加危险开关。显式低权限 SHALL 优先；resume SHALL 保留原任务模式，followup 可显式覆盖。此模式跳过工具审批但 SHALL NOT 宣称绕过 OS 权限或提供目录沙箱。SHALL 拒绝任务文件、任务目录及读取文件的任何祖先为符号链接。

#### Scenario: 非法输入
- **Given** 缺少必填字段、含路径穿越字符、非法 ID 格式、未知权限模式或符号链接路径
- **When** 调用任何子命令
- **Then** 显式报错退出，不执行 CLI。

### Requirement: 私有输出与身份隔离
输出 SHALL 存储于本 checkout ignored 的 `tmp/qoder-tasks/<run-id>/`（目录权限 0700，文件权限 0600）。SHALL 保留独立 `client=qoder` 身份及 `parent_client`/`parent_session_id` 关联。SHALL NOT 读取私人原始 session 文件或自动读取长日志。

#### Scenario: 身份保留
- **Given** 任何任务执行
- **When** 记录完成信息
- **Then** 保存精确 Qoder session id、client、parent_client、parent_session_id，不冒用其他客户端身份。

### Requirement: 状态语义
`status` 对未知 run_id SHALL 非零退出。运行中的 worker SHALL 记录 PID 供单次判定。Worker 死亡且无完成记录 SHALL 显示 `unknown`。CLI 非零退出 SHALL 标记 `failed`；exit 0 SHALL 标记 `finished`（非 `PASS`）。`result` SHALL 给出报告/日志路径与有限结果正文。`resume` 缺 session 或未完成 SHALL 非零退出，不新开空会话。

#### Scenario: 状态查询
- **Given** 任务 run_id
- **When** 调用 `status` 或 `result`
- **Then** 未知 run_id 非零退出；运行中显示 PID；已完成显示 `finished`/`failed` 及日志路径。

### Requirement: 默认实现归属
Codex 担任主调度时，功能、修复、重构、测试、脚本、配置、文档等修改 SHALL 默认派发给 Qoder 实现。Codex SHALL 自行处理极小修改、设计决策，或在 Qoder 不可用、权限不足、两轮返工不收敛时接管并说明理由。任务粒度 SHALL 为单一可验收目标。返工 SHALL 最多 2 轮。派发前 SHALL 公开 task id、目标/来源、读写与禁止范围、上下文、验收条件、权限模式、失败策略和版本变化。Codex 与单个 Qoder 的并行 SHALL 避开写写、读写、接口变更和运行输出冲突；集成验证 SHALL 串行。Qoder SHALL NOT 递归委派给自身。当前通过 codex queue 排入完成回调，但不保证消息已消费，未实现自动重发、取消或 OS 沙箱，文档 SHALL 如实说明能力边界。

#### Scenario: 派发可见性
- **Given** Codex 派发修改任务给 Qoder
- **When** 派发前
- **Then** 任务卡包含 task_id、goal_or_source、allowed_files、forbidden_files、required_context、acceptance_criteria、permission_mode、failure_policy、change_version。

#### Scenario: 返工上限
- **Given** Qoder 实现结果未通过 Codex 复核
- **When** 已达 2 轮返工
- **Then** Codex 接管并说明理由，不再继续委派。

### Requirement: Qoder 单任务调度
主调度 SHALL 限制同时运行的 Qoder 任务数为 1，其他任务排队；确认前一个任务结束才启动下一个。SHALL NOT 默认利用短时双任务重叠、另开 session 或递归委派绕过限制。该限制当前由主调度遵守，SHALL NOT 宣称脚本已有跨进程互斥锁或自动队列。

#### Scenario: 前一任务状态不明
- **Given** 前一 Qoder 任务尚未确认结束
- **When** 新任务或返工准备派发
- **Then** 保留待派发任务，不启动第二个 Qoder；Codex 可做无冲突的独立工作，没有独立工作时结束回合，不循环查询。

### Requirement: Codex 父会话回调
parent_client 为 codex 的子任务 SHALL 绑定精确父会话 UUID。新任务缺省 parent_session_id 时可从 CODEX_THREAD_ID 补全并持久化；非法目标 SHALL 拒绝启动。恢复时 SHALL 保留原绑定，不使用 --last、名称或环境中的另一会话。

worker SHALL 在成功、非零退出或异常后先写 completion.json，再用 codex queue 请求父会话复核。通知 SHALL 仅包含运行标识、结果位置和固定复核指令，不复制原始日志。callback.json SHALL 独立记录 queued/failed/unknown，回调失败不覆盖任务结果；同一 run SHALL 不自动重复发送。queued SHALL NOT 等同消息已消费或任务 PASS。

#### Scenario: 完成自动接续
- **Given** 父会话绑定有效，Codex CLI 与服务可用
- **When** Qoder 退出并保存结果
- **Then** 原父会话获得复核消息并读取同一 run 的结果；真实接续须单独验收。

#### Scenario: 回调失败或状态不确定
- **Given** Codex 不可用、回调超时或回执写入中断
- **When** 回调不能确认成功
- **Then** 保留完成记录，明确回调失败或不确定，不自动重发，不宣称父会话已接续。
