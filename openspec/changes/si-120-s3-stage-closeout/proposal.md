# SI-120: S3 Scan/Index 所有权与 Stage 收口

## 动机

S3 stage 最终收口任务。SI-110 已退休 Python scan 写路径，确立 Java 为唯一 scan/index producer。
本任务执行只读验证、ownership 文档同步和 stage marker 生成，确认 S3 stage 完整达成。

## 范围

- 冷构建和 warm cache 复验
- 全/增量/后台 scan 所有权验证
- Python 只读 query/Web smoke 验证
- S3-ACCEPTED marker 生成
- durable ownership 文档更新

## 约束

- 不修改 production 代码
- 不修改 forbidden scope 内任何文件
- 不新增公共 type 或 module
- 只做验证、文档同步和 artifact 生成

## 验收标准

- 所有质量门禁通过
- scan/index 仅 Java 写
- Python 只读 query/Web
- 0 skipped/aborted
- production closeout diff 为空
- S3-ACCEPTED marker 存在
- ownership 文档已更新
