# Agent Run Profiler

> 面向本地 Claude Code / Codex 的桌面端会话索引与 Token 分析工具

该工具默认面向电脑浏览器使用，不做 mobile 适配。页面保持固定侧栏、宽表格和桌面最小宽度，窄窗口下通过浏览器横向滚动查看完整内容。

## 快速开始

### 本地运行

```bash
# 安装依赖
./scripts/session-browser.sh deps

# 扫描到本地测试索引（首次约 8 秒）
./scripts/session-browser.sh scan

# 前台启动本地服务（DEBUG 日志，适合大模型修改 tool 后验证）
./scripts/session-browser.sh serve

# 浏览器打开 http://127.0.0.1:18999
```

本地测试启动只走前台进程，不提供后台静默启动命令。关闭终端进程或按 `Ctrl-C` 后，本地测试服务会立即退出。默认端口和索引目录与 Podman 隔离：

| 场景 | 地址 | SQLite index |
|------|------|--------------|
| 本地测试 `serve` / `scan` | `http://127.0.0.1:18999` | `~/.local/share/feipi/session-browser/local-test-index/` |
| Podman 部署 | `http://127.0.0.1:8899` | `~/.local/share/feipi/session-browser/index/` |

### Podman 本地部署

```bash
# 查看当前版本
./scripts/session-browser.sh version

# 修改版本号（可选）
./scripts/session-browser.sh set-version 0.2.0

# 测试后构建本地镜像：localhost/feipi/session-browser:0.2.0 和 :latest
./scripts/session-browser.sh release 0.2.0

# 用本地镜像启动 Podman 容器
./scripts/session-browser.sh podman-up 0.2.0

# 或者一步完成：构建镜像并部署到本地
./scripts/session-browser.sh deploy 0.2.0

# 查看日志 / 状态 / 停止
./scripts/session-browser.sh podman-logs
./scripts/session-browser.sh podman-status
./scripts/session-browser.sh podman-down
```

容器将 `~/.claude`、`~/.codex`、`~/.qoder` 以只读方式挂载，index 默认持久化在 `~/.local/share/feipi/session-browser/index/`。该目录只给 Podman 使用，本地测试默认不会读写它。升级镜像或重建容器时，只要该目录不删除，索引会继续复用。本地镜像默认使用：

```text
localhost/feipi/session-browser:<VERSION>
localhost/feipi/session-browser:latest
```

### 发布流

版本管理以 `VERSION` 文件为真源，推荐流程：

1. 修改代码后执行 `./scripts/session-browser.sh serve`，在 `http://127.0.0.1:18999` 前台观察访问日志和错误堆栈。
2. 执行 `./scripts/session-browser.sh test`，通过单元测试。
3. 确认版本号：`./scripts/session-browser.sh set-version <x.y.z>`。
4. 执行 `./scripts/session-browser.sh release <x.y.z>`，测试通过后构建本地 Podman 镜像。
5. 执行 `./scripts/session-browser.sh podman-up <x.y.z>`，用指定版本镜像部署到本地。

如需单条命令完成打包和部署，可使用 `./scripts/session-browser.sh deploy <x.y.z>`。

容器启动命令默认会传入 `--startup-scan`：服务监听前先做一次全窗口增量扫描，避免首次启动空白；随后后台扫描器会持续定时刷新，hot 会话每 30 秒扫描，warm 会话每 5 分钟扫描。数据源只读挂载，SQLite index 单独持久化。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CLAUDE_DATA_DIR` | `~/.claude` | Claude Code 数据目录 |
| `CODEX_DATA_DIR` | `~/.codex` | Codex 数据目录 |
| `QODER_DATA_DIR` | `~/.qoder` | Qoder 数据目录 |
| `INDEX_DIR` | `~/.local/share/feipi/session-browser/local-test-index` | 本地前台测试索引目录 |
| `SERVER_HOST` | `127.0.0.1` | 本地前台测试服务绑定地址 |
| `SERVER_PORT` | `18999` | 本地前台测试服务端口 |
| `SESSION_BROWSER_LOG_LEVEL` | `INFO` | 日志级别；本地 `serve` 默认 `DEBUG` |
| `SESSION_BROWSER_VENV_DIR` | `./.venv` | 本地依赖虚拟环境目录 |
| `SESSION_BROWSER_LOCAL_HOST` | `127.0.0.1` | 本地 `serve` 默认绑定地址 |
| `SESSION_BROWSER_LOCAL_PORT` | `18999` | 本地 `serve` 默认端口 |
| `SESSION_BROWSER_LOCAL_DATA_DIR` | `~/.local/share/feipi/session-browser/local-test-index` | 本地 `serve` / `scan` 默认索引目录 |
| `SESSION_BROWSER_IMAGE_REPO` | `localhost/feipi/session-browser` | Podman 本地镜像仓库 |
| `SESSION_BROWSER_CONTAINER_NAME` | `session-browser` | Podman 容器名 |
| `SESSION_BROWSER_HOST_PORT` | `8899` | Podman 宿主机映射端口 |
| `SESSION_BROWSER_DATA_DIR` | `~/.local/share/feipi/session-browser/index` | Podman index 持久化目录 |
| `SESSION_BROWSER_STARTUP_SCAN` | `1` | 容器启动时先扫描一次再监听 |

## 页面

| 页面 | 路径 | 内容 |
|------|------|------|
| Dashboard | `/dashboard` | 紧凑指标卡片、趋势图、项目/会话列表 |
| Projects | `/projects` | 所有项目聚合，含 Cache Read/Write 列 |
| Project | `/projects/{key}` | 项目级统计 + 会话列表 |
| Sessions | `/sessions` | 全局会话列表，支持 Agent/Model/Project 过滤 |
| Session | `/sessions/{agent}/{id}` | 折叠对话轮次、Token 柱状图、Token Profile、Tool 树 |
| Agents | `/agents` | Agent 级统计 |
| Token Glossary | `/glossary` | Token 指标定义与 Provider 映射 |

## 快捷键

| 键 | 操作 |
|----|------|
| `/` | 聚焦当前页面的过滤框 |
| `t` | 切换到 Token Profile 标签 |
| `m` | 切换到 Messages 标签 |
| `r` | 切换到 Raw 标签 |
| `Esc` | 折叠所有展开的对话轮次 |

## Token 指标

| 指标 | 说明 |
|------|------|
| **Input Fresh** | 实际新发送的输入 Token（未命中缓存） |
| **Cache Read** | 缓存命中的输入 Token（输入侧读） |
| **Cache Write** | 写入缓存的输入 Token（输入侧写） |
| **Output** | 可见输出 Token |

注意：Cache Read ≠ 输出缓存。`cache_read_input_tokens` 和 `cache_creation_input_tokens` 都是输入侧字段。

### Qoder Token 估算

Qoder 客户端日志不携带真实的 usage/token 统计。session-browser 会对每个 LLM call 做**本地快速估算**：

- **估算方法**：`qoder-fast-bytes-v1` — 按 UTF-8 字节长度启发式（`tokens ≈ bytes / 3.5`），有 tiktoken 时优先使用 `cl100k_base`；单段文本上限 32KB，超出部分截断后计数。
- **精度标记**：UI 中显示为 `estimated`（琥珀色），而非 `provider-reported`。
- **上下文累积**：每轮 assistant 的 input_tokens = 当前可见上下文累积大小，后续轮次的 input_tokens 自然递增。
- **Cache 字段**：Qoder 没有缓存指标，cache_read / cache_write 一律填 0，不做臆造。
- **误差范围**：估算值不精确到 API 级别的 token 数，但足够用于趋势对比、热点轮次定位和相对大小比较。

## Claude Code 子 Agent 诊断

Claude Code 的父会话文件只记录主会话的 `Agent` 工具调用；子 Agent 内部的真实工具循环会写到同级目录：

```text
~/.claude/projects/<project>/<session-id>/subagents/*.jsonl
```

`session-browser` 会把这些 sidechain 文件合并到父 session 的诊断视图：

- 会话级 `Tools` 包含主会话工具调用和子 Agent 内部工具调用。
- `Tools` 页会用 `Scope` 标记 `main` 或 `subagent`。
- `Rounds` 表新增 `LLM` 列，显示该 round 的主模型调用数和嵌套 Agent 内部模型调用数。
- `Agent` 工具行会显示子 Agent 摘要，包括 `LLM` 调用数、内部工具调用数和工具分布。

LLM 调用数基于 Claude Code JSONL 中唯一 `assistant.message.id` 推断。它能反映已经落盘的模型响应；如果要精确看到 LiteLLM 层的 HTTP 重试、失败状态和未落盘请求，需要后续接入 LiteLLM proxy 日志或数据库作为补充数据源。

## 目录结构

```
feipi-session-browser/
├── Dockerfile                      # 容器镜像
├── VERSION                         # 本地发布版本真源
├── pyproject.toml                  # 包配置、pytest 设置
├── requirements.txt                # 运行依赖
├── requirements-dev.txt            # 本地测试依赖
├── .dockerignore
├── .gitignore
├── compose/
│   └── docker-compose.yml          # 可选 compose 兼容入口
├── env/
│   └── .env.example                # 环境变量模板
├── scripts/
│   ├── session-browser.sh          # 启动脚本
│   └── harness/
│       └── doctor.sh               # harness 检查
├── src/
│   └── session_browser/
│       ├── config.py               # 配置中心（环境变量）
│       ├── cli.py                  # CLI 入口
│       ├── domain/
│       │   ├── models.py           # 数据模型
│       │   └── token_normalizer.py # Token 标准化器
│       ├── sources/
│       │   ├── claude.py           # Claude Code 解析器
│       │   ├── codex.py            # Codex 解析器
│       │   └── qoder.py            # Qoder 解析器（含快速 token 估算）
│       ├── index/
│       │   ├── indexer.py          # SQLite 索引
│       │   └── metrics.py          # 聚合统计
│       └── web/
│           ├── routes.py           # HTTP 服务
│           └── templates/          # Jinja2 模板
├── tests/
│   ├── fixtures/                   # 测试数据
│   ├── test_token_normalizer.py    # Token 标准化测试
│   ├── test_qoder_token_estimation.py  # Qoder token 估算测试
│   ├── test_make_round.py          # Round 构建与 token 提取测试
│   └── test_title_extraction.py    # 标题提取测试
```

## 隐私

- **只读**：不修改任何原始数据
- **本地**：数据源目录以只读方式挂载
- **脱敏**：敏感字段默认隐藏

## Troubleshooting：orphan `-zsh` 高 CPU

`session-browser` 本身不创建 `zsh`、`zpty`、`pty` 或交互式 shell。启动脚本会用 `exec python3 -m session_browser ...` 替换当前脚本进程，避免额外的父 shell 长期驻留；`stop` 命令只短暂调用 `lsof` 查找端口，并在 timeout 时清理子进程组。

如果 Activity Monitor 中看到高 CPU 的 `-zsh`，可先确认是否为外部 agent/terminal executor 在本目录遗留的 login shell：

```bash
ps -axo pid,ppid,pgid,sess,tty,stat,etime,%cpu,%mem,command \
  | grep -E 'session-browser|python3 -m session_browser|-zsh' \
  | grep -v grep
```

重点看这些信号：

- `COMMAND=-zsh`：login zsh，不是 `python3 -m session_browser`。
- `PPID=1`：原父进程已退出，进程被 `launchd(1)` 收养。
- `TTY=??`：没有真实终端窗口，常见于 agent/executor 创建的伪终端。
- `STAT=R` 或 `U` 且 CPU 高：不是 idle shell。

确认 cwd：

```bash
lsof -a -p <pid> -d cwd
```

检查是否有未回收的 zombie child：

```bash
ps -axo pid,ppid,pgid,stat,etime,%cpu,%mem,command | awk -v p="<pid>" '$2 == p {print}'
```

如果确认目标 PID 是已知的 orphan `-zsh`，可先温和结束指定 PID：

```bash
kill <pid1> <pid2>
sleep 2
ps -ww -p <pid1>,<pid2> -o pid,ppid,stat,etime,%cpu,command
```

若仍未退出，再对同一批已确认 PID 使用：

```bash
kill -9 <pid1> <pid2>
```
