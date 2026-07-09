# 密钥和 token

以下字段视为敏感，默认隐藏：

- `sk-` 开头的 API token（如 Anthropic API key）。
- `sk-ant-` 开头的 Anthropic 专属 token。
- `ghp_`、`gho_`、`ghs_` 开头的 GitHub token。
- `Bearer ` 后跟的长串 token。
- 任何以 `token`、`api_key`、`secret`、`password` 命名的字段值。

处理规则：展示时用 `<REDACTED>` 替换，日志中省略完整值只保留前 4 字符加 `***`。

## HTTP header

以下 header 值视为敏感：

- `Authorization` — 包含 Bearer token 或 Basic 凭证。
- `Cookie` / `Set-Cookie` — 包含 session cookie。
- `X-Api-Key` — API 密钥。
- `X-Auth-Token` — 认证 token。

处理规则：导出时替换为 `<REDACTED>`，日志中只记录 header 名称不记录值。

## 本地路径

以下路径模式视为敏感：

- macOS 用户 home 目录（`~/` 展开后的绝对路径）。
- Linux 用户 home 目录（`~/` 展开后的绝对路径）。
- Windows 用户目录（盘符加用户目录的绝对路径）。
- `~/.claude/`、`~/.codex/`、`~/.qoder/` 的真实绝对路径。

处理规则：使用 `~/.claude` 等 tilde 缩写或占位符替代。文档中允许 `~/.claude` 写法。

## 原始 request / response

以下原始数据视为敏感：

- 完整 request body 包含用户 prompt。
- 完整 response body 包含模型输出。
- 包含用户个人信息的 API response。

处理规则：只展示最小化片段，使用 synthetic 样例替代真实数据。

## 用户输入内容

以下内容视为敏感：

- 用户 prompt 原文。
- 用户粘贴的代码或文件内容。
- 用户邮箱、姓名等个人信息。

处理规则：使用合成内容替代，展示时标注 `[用户输入已脱敏]`。

## 日志和错误栈

以下内容视为敏感：

- 包含完整 token 的错误栈。
- 包含本地路径的异常信息。
- 包含用户数据的日志行。

处理规则：错误栈中路径使用占位符，token 使用 `<REDACTED>`，日志级别降低时自动脱敏。
