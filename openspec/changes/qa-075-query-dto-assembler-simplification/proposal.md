# QA-075: Query/DTO/Assembler 专题精简与 SQL 优化

## 动机

消除 query/application 模块中的冗余 SQL 条件、row mapping、DTO 转换和跨层校验。

## 范围

- 消除重复 SQL 条件构建
- 合并 row mapping 公共逻辑
- 简化 DTO 转换
- 删除低价值跨层校验重复

## 约束

- 不修改 query/application API 契约
- 不新增公共 type
- 只处理高置信精简

## 验收标准

- 所有测试通过
- API 快照无漂移
- 增量复用分析无新增 P0/P1
