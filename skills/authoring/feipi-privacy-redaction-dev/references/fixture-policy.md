# Synthetic fixture 优先

所有测试 fixture 优先使用合成数据（synthetic fixture）。合成数据要求：

- 结构与真实数据一致。
- 值使用占位符或明显假数据（如 `dummy-token-12345`）。
- 不包含任何真实 session 内容。
- 文件中标注 `synthetic` 标记。

## 真实 session 禁止入仓

以下真实数据禁止进入仓库：

- `~/.claude/projects/` 下的真实 session 文件。
- `~/.codex/sessions/` 下的真实 session 文件。
- `~/.qoder/` 下的真实数据文件。
- 包含真实用户 home 绝对路径的 fixture。
- 包含真实 API key 或 token 的任何文件。

gate 脚本 `repository.no-real-session-fixtures` 和 `security.secret-like-content` 负责检测。

## 允许的最小样例

以下最小样例允许入仓：

- 文档中使用 `~/.claude`、`~/.codex`、`~/.qoder` 占位符。
- 结构示例中使用 `<placeholder>` 值。
- 配置模板中使用 `REDACTED`、`dummy`、`example` 值。
- 测试 fixture 使用明确标注为 synthetic 的数据。

## 文件命名

fixture 文件命名规则：

- synthetic fixture 放在 `tests/fixtures/synthetic/` 下。
- 文件名包含 `synthetic` 或 `sample` 标识。
- 不使用真实用户路径或 token 作为文件名。
- 大 JSONL fixture 必须在 synthetic 目录下。

## Review checklist

代码审查时检查：

- [ ] fixture 是否 synthetic？
- [ ] 是否包含真实 home 路径？
- [ ] 是否包含真实 token 或密钥？
- [ ] 文件路径是否使用占位符？
- [ ] 是否在 `tests/fixtures/synthetic/` 目录下？
- [ ] 是否通过了 `repository.no-real-session-fixtures`？
- [ ] 是否通过了 `security.secret-like-content`？
