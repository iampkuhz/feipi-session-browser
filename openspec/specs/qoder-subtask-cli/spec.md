# Qoder Subtask CLI

## Status
ADDED

## Requirements

### Requirement: 显式低开销委派
脚本 SHALL 显式启动带完整 handoff 与独立身份的 qodercli 子任务，立即返回唯一 run id（UUID）。SHALL NOT 持续轮询、无限续跑、默认跳过权限或自动进行 Git mutation。

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
任务输入 SHALL 为包含完整九项 handoff 的 JSON。参数 SHALL 以数组传递（无 `shell=True`/`eval`）。Run ID SHALL 使用 UUID 格式。`permission_mode` SHALL 仅接受 `default`/`accept_edits`/`dont_ask`，拒绝 `bypass_permissions` 等危险标志。SHALL 拒绝任务文件、任务目录及读取文件的任何祖先为符号链接。

#### Scenario: 非法输入
- **Given** 缺少必填字段、含路径穿越字符、非法 ID 格式、危险权限模式或符号链接路径
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
