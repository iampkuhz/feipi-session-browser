# Feipi Session Browser

本工具用于在本机浏览 Claude Code、Codex、Qoder 等 agent 会话记录，并查看项目、会话列表、会话详情和 Token 统计。

## 快速启动

```bash
# 构建 Java launcher（首次使用或代码变更后需要）
./gradlew :java:app-cli:installDist

# 扫描本机会话数据，生成本地索引
./scripts/session-browser.sh scan

# 前台启动本地服务（Java launcher）
./scripts/session-browser.sh serve
```

启动后打开：

```text
http://127.0.0.1:8848
```

本地服务以前台进程运行。关闭终端进程或按 `Ctrl-C` 后，服务会立即退出。

## 常用命令

```bash
# 查看当前版本（Java CLI）
./scripts/session-browser.sh version

# 重新扫描会话数据
./scripts/session-browser.sh scan

# 前台启动服务（Java launcher）
./scripts/session-browser.sh serve

# 按端口停止本地服务进程（Java launcher）
./scripts/session-browser.sh stop --port 8848

# 查看所有可用命令（Java CLI）
./scripts/session-browser.sh help
```

## 默认数据位置

| 数据 | 默认目录 |
|---|---|
| Claude Code 会话 | `~/.claude` |
| Codex 会话 | `~/.codex` |
| Qoder 会话 | `~/.qoder` |
| 本地索引 | `~/.local/share/feipi/session-browser/local-test-index/` |

会话源目录只读使用；本工具不会修改原始会话文件。

## 常用环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `CLAUDE_DATA_DIR` | `~/.claude` | Claude Code 数据目录 |
| `CODEX_DATA_DIR` | `~/.codex` | Codex 数据目录 |
| `QODER_DATA_DIR` | `~/.qoder` | Qoder 数据目录 |
| `SESSION_BROWSER_LOCAL_HOST` | `127.0.0.1` | 本地服务绑定地址 |
| `SESSION_BROWSER_LOCAL_PORT` | `8848` | 本地服务端口 |
| `SESSION_BROWSER_LOCAL_DATA_DIR` | `~/.local/share/feipi/session-browser/local-test-index` | 本地索引目录 |
| `SESSION_BROWSER_LOG_LEVEL` | `INFO` | 日志级别 |
| `SESSION_BROWSER_VENV_DIR` | `./.venv` | 本地虚拟环境目录（仅用于 Python 开发工具） |

示例：使用自定义端口启动。

```bash
./scripts/session-browser.sh serve --port 19000
```

示例：使用自定义索引目录扫描。

```bash
SESSION_BROWSER_LOCAL_DATA_DIR=/tmp/session-browser-index ./scripts/session-browser.sh scan
```

## 页面入口

| 页面 | 路径 |
|---|---|
| Dashboard | `/dashboard` |
| Projects | `/projects` |
| Sessions | `/sessions` |
| Token Glossary | `/glossary` |
| Session Detail | `/sessions/{agent}/{id}` |

## 隐私说明

- 原始会话目录只读使用。
- 索引默认保存在本机用户目录下。
- 敏感字段在页面中默认隐藏。
