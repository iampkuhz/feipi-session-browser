# 任务账本

> 本文件是 agent 执行任务的状态源。单次迁移或开发任务应按序更新状态，并在最终报告中说明验证结果。

## 协议版本

- 协议：single-session-serial v1
- 当前任务编号：001

## 状态枚举

- `pending`
- `in_progress`
- `blocked`
- `done`

## 任务表

| ID | 任务 | 状态 | 验证 | 结果 |
|----|------|------|------|------|
| 001 | 项目基线检查 | pending | `git status --short` | 待记录 |
| 002 | 本地依赖安装 | pending | `./scripts/session-browser.sh deps` | 待记录 |
| 003 | 单元测试 | pending | `./scripts/session-browser.sh test` | 待记录 |
| 004 | Harness 检查 | pending | `bash scripts/harness/doctor.sh` | 待记录 |
