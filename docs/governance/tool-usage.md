# 工具使用规范

目标：降低工具输出噪声，避免误读大文件和误提交本地数据。

## 推荐命令

| 场景 | 推荐 | 避免 |
|------|------|------|
| 文件清单 | `rg --files`、`find . -maxdepth 3 -type f` | 无限制 `find . -type f` |
| 文本搜索 | `rg -n "pattern" path` | 全仓库 `grep -rn` 后再整文件读取 |
| 局部读取 | `sed -n '1,120p' file` | 对大文件整文件输出 |
| JSON/YAML | `jq`、`python3 -m json.tool` | 手写脆弱字符串解析 |
| Git diff | `git diff --stat` 后看单文件 diff | 无限制 `git diff` |
| 测试输出 | 保留 100 行内关键失败 | 原样贴超长日志 |

## Session 数据

- 原始数据目录 `~/.claude`、`~/.codex`、`~/.qoder` 只读。
- 不要读取完整大型 JSONL；优先抽样、按字段提取、按 session id 定位。
- 不要把真实 session 文件复制进仓库。

## 个人配置

以下文件属于本地配置，不应提交：

- `.claude/settings.local.json`
- `.mcp.json`
- `.env`
- `data/`
- `output/`
- `.venv/`
- `.pytest_cache/`
