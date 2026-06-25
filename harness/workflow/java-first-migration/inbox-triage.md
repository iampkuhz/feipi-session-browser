# Inbox Triage 流程

本文档定义从 USER-INBOX.md 到 ISSUE-BOARD.md 的 triage 规则。

## 触发时机

- **task 结束后**：每个 scoped task 完成后，读取 USER-INBOX.md 中的新增 block。
- **phase 边界**：每个 phase 的 validation 之前和之后。
- **用户主动要求**：用户明确说"新增观察"或"triage inbox"时。

不得在子任务执行中途触发 triage，不打断当前任务。

## 读取规则

1. 扫描 USER-INBOX.md 中所有 `<!-- MIGRATION-OBSERVATION:BEGIN -->` 到 `<!-- MIGRATION-OBSERVATION:END -->` 之间的 block。
2. 跳过示例 block（标题含"示例"字样的）。
3. 对比 ISSUE-BOARD.md 中已有 Issue ID，识别新增 observation。

## 分类规则

对每条新增 observation，执行以下分类：

| 分类 | 条件 |
|---|---|
| `ASSIGNED` | 能明确映射到已规划的未来 task 或 phase。 |
| `DUPLICATE` | 与 ISSUE-BOARD.md 中已有条目的摘要语义重复。 |
| `OUT_OF_SCOPE` | 不属于本迁移任务的范围（如产品功能建议、其他仓库的问题）。 |
| `BLOCKED` | 需要用户进一步决策或依赖外部条件才能处理。 |

## Issue ID 生成规则

- 格式：`OBS-YYYYMMDD-<hash6>`
- `YYYYMMDD`：observation 首次 triage 的日期。
- `hash6`：对 observation 标题取 SHA-256，取前 6 位十六进制字符。
- 同一标题不会产生重复 ID（因为同标题会被分类为 DUPLICATE）。

## 输出

Triage 完成后输出：

- 新增 issue 数量。
- 每个 issue 的分类结果和分配任务（如有）。
- 是否存在 BLOCKED 条目需要用户决策。
