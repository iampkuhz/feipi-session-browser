# QA-090: S4 Query/Application API 冻结与 Stage 收口

## 动机

S4 stage 最终收口任务。QA-080 已完成 query parity、只读和性能门禁。
本任务执行只读验收、ownership 文档同步和 stage marker 生成，确认 S4 stage 完整达成。

## 范围

- 冷构建和 warm cache 复验
- query/application 所有权验证
- S4-ACCEPTED marker 生成
- durable ownership 文档更新

## 约束

- 不修改 production 代码
- 不修改 forbidden scope 内任何文件
- 不新增公共 type 或 module
- 只做验证、文档同步和 artifact 生成

## 验收标准

- 所有质量门禁通过
- Java 可独立生成全部 Web 所需模型
- Python Web 仍可运行
- 0 skipped/aborted
- production closeout diff 为空
- S4-ACCEPTED marker 存在
- ownership 文档已更新
