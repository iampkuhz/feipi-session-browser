# SI-100 Design: Java Scan CLI、Shell 路由与用户行为 Cutover

## 架构

### CLI 层（ScanCommand）

`ScanCommand` 实现 `Callable<Integer>`，通过 Picocli 注册为 `scan` 子命令。

参数解析（CLI 边界校验，不重复）：
- `--full` / `--incremental` — 扫描模式（互斥，手动检查）
- `--agent` — 源过滤（claude_code/codex/qoder）
- `--force` / `-f` — 非交互模式标志

执行流程：
1. 解析 INDEX_DIR 环境变量（或默认路径）
2. 创建索引目录和 artifact 输出目录
3. 构建源条目列表（根据 agent 过滤和环境变量解析根目录）
4. 获取 ScanLock（阻塞模式，超时可通过环境变量配置）
5. 创建 SQLite 连接，执行 full 或 incremental scan
6. 打印汇总输出，返回退出码

### Shell 路由

`session-browser.sh` 的 `run_scan` 函数：
- 定位 Java launcher（`java/app-cli/build/install/app-cli/bin/app-cli`）
- launcher 缺失时中文报错、非零退出、不 fallback 到 Python
- 设置 INDEX_DIR 环境变量，exec Java launcher

### 校验放置

| 校验位置 | 校验内容 |
|---|---|
| CLI/Picocli | 参数语法、未知选项、--full/--incremental 互斥 |
| ScanCommand | INDEX_DIR 目录创建、agent 过滤器合法性 |
| ScanLock | OS 级文件锁互斥 |
| SourceAdapter.checkRoot | 根目录安全性 |
| ConnectionFactory | JDBC 连接配置 |
| SQLite constraint | 行级约束 |

### 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 扫描成功 |
| 1 | 扫描过程出错（IO、解析、归一化等） |
| 2 | 扫描锁冲突或数据库被锁定 |

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| INDEX_DIR | ~/.local/share/feipi/session-browser/local-test-index | 索引目录 |
| CLAUDE_DATA_DIR | ~/.claude | Claude 数据根目录 |
| CODEX_DATA_DIR | ~/.codex | Codex 数据根目录 |
| QODER_DATA_DIR | ~/.qoder | Qoder 数据根目录 |
| SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS | 30 | 扫描锁超时（秒） |

## 复用

- FullScanEngine / IncrementalScanEngine — scan engine 复用
- ScanLock — 跨进程锁复用
- ConnectionFactory — SQLite 连接复用
- ClaudeSourceAdapter / CodexSourceAdapter / QoderSourceAdapter — 源适配器复用
- ScanConfig — 扫描配置复用
- ScanSummary / IncrementalScanSummary — 汇总输出复用
