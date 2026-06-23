# AC-090: S2C 所有权、CI 与 Stage 收口

## 动机

S2C stage 最终收口任务。AC-080 已删除 Python writer 并确立 Java 为唯一 canonical artifact producer。
本任务执行只读验证、ownership 文档同步和 stage marker 生成，确认 S2C stage 完整达成。

## 范围

- 冷构建和 warm cache 复验
- 三来源 full/incremental/tiered synthetic scan 验证
- artifact/source 隐私和只读 AST 证明
- S2C-ACCEPTED marker 生成
- durable ownership 文档更新
- OpenSpec change ac-090-s2c-stage-close 创建

## 约束

- 不修改 production 代码
- 不修改 forbidden scope 内任何文件
- 不新增公共 type 或 module
- 只做验证、文档同步和 artifact 生成

## 验收标准

- 所有质量门禁通过
- Java 是 canonical JSON/meta 唯一 producer（AST 证明）
- Python 仍拥有 scan orchestration/SQLite
- 0 skipped/aborted
- S2C-ACCEPTED marker 存在
- ownership 文档已更新
