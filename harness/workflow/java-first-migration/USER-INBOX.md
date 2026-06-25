# USER-INBOX.md

用户只在文件底部追加观察。Agent 不要重写用户原文，不要中途频繁读取；只在每个子任务结束后或 phase 边界读取新增 block。

## 使用规则

- 每条观察用 `<!-- MIGRATION-OBSERVATION:BEGIN -->` 和 `<!-- MIGRATION-OBSERVATION:END -->` 包裹。
- Agent 不修改或删除用户原文，状态维护在 `ISSUE-BOARD.md`。
- Agent 只在 task 结束后或 phase 边界读取新增 block，不会中途打断子任务。

## 示例 block（仅供参考格式，请勿修改或删除）

<!-- MIGRATION-OBSERVATION:BEGIN -->

## 示例：迁移观察条目格式说明

- 位置：
  相关路径、模块、页面或命令。

- 现象：
  1. 具体问题 1
  2. 具体问题 2

- 我希望：
  1. 预期改法或偏好
  2. 不能接受的做法

- 优先级：
  高 / 中 / 低

- 补充：
  任何上下文。

<!-- MIGRATION-OBSERVATION:END -->

## 用户观察追加区

<!-- 在下方追加 MIGRATION-OBSERVATION block -->
