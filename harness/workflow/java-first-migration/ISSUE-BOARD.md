# ISSUE-BOARD.md

Agent 维护本文件，用于把 USER-INBOX 的观察转成可执行任务。不要删除历史记录；状态变化追加记录或更新 task 表。

## 状态枚举

- `NEW`：刚识别，尚未分配。
- `TRIAGED`：已分类。
- `ASSIGNED`：已分配到未来 task。
- `IN_PROGRESS`：正在处理。
- `DONE`：已处理并验证。
- `DUPLICATE`：重复。
- `OUT_OF_SCOPE`：不属于本迁移任务。
- `BLOCKED`：需要用户决策或外部条件。

## 问题表

| Issue ID | 来源 | 摘要 | 优先级 | 状态 | 分配任务 | 验收标准 | 备注 |
|---|---|---|---|---|---|---|---|

## 处理规则

1. 每个 observation 用稳定 hash 生成 ID，格式 `OBS-YYYYMMDD-<hash6>`，其中 `hash6` 为 observation 标题的 SHA-256 前 6 位。
2. 不在用户原文里插入状态，状态写到本文件。
3. 能映射到现有任务的，填 `分配任务`。
4. 无法映射的，新建 future task proposal，但不要立刻扩散实现。
5. 每个 phase validation 前后检查一次，不要在子任务中途频繁打断。
6. 分类结果必须是以下之一：`ASSIGNED`、`DUPLICATE`、`OUT_OF_SCOPE`、`BLOCKED`。
7. 不删除任何行，只做状态更新和追加。
