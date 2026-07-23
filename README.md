# Feipi Session Browser

本工具用于在本机浏览 Claude Code、Codex、Qoder 等 agent 会话记录，并查看项目、会话列表、会话详情和 Token 统计。

## 快速启动

```bash
# 准备产品运行时（构建 Java launcher + preflight）
./scripts/session-browser.sh deps

# 扫描本机会话数据，生成本地索引；没有会话源目录时会创建空索引
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
# 准备或修复 Java launcher
./scripts/session-browser.sh deps

# 安装 Python 开发/测试依赖（仅开发质量门需要）
./scripts/session-browser.sh deps --dev

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
| `SESSION_BROWSER_LOG_LEVEL` | `WARN` | 日志级别 |
| `SESSION_BROWSER_VENV_DIR` | `./.local/python/venv` | 本地虚拟环境目录（仅用于 `deps --dev` 和 Python 开发工具） |

完整示例见 [`config/env/session-browser.env.example`](config/env/session-browser.env.example)。

## 仓库内生成路径

- 根 `tmp/` 保留为 Hook、Gate 和 Playwright fallback 的本地 runtime 父目录；其中 evidence
  按 client/session/run 隔离。
- 根 `.local/` 保存可再生的 Gradle 与 Python 产物：Python venv/cache/coverage 位于
  `.local/python/`，根 Gradle cache/build 位于 `.local/gradle/`。
- Playwright 项目与 `node_modules/` 位于 `tests/playwright/`；Java module build 仍位于各
  `java/**/build/`。
- `FEIPI_AGENT_RUNTIME_ROOT` 的既有优先级不变；未设置时 Playwright 继续 fallback 到
  `<repoRoot>/tmp/agent-runtime/`。
- `python3 -m scripts.checks repository.misplaced-generated-paths` 会直接检查磁盘上的旧路径，
  即使路径被 ignore 也不会静默通过。

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
