# 数据索引验收范围

SQLite schema、查询过滤和持久化由 Java 模块测试覆盖；全量、增量、坏文件隔离和索引发布由 Java 扫描契约及 `scanCommandSmoke` 验证。交付时使用根 `check` 和统一 Gate，不维护退役 Python 测试清单。

每个发布版本从原始会话重建独立索引；同版本保留增量更新。详见[发行与本机安装](../../release/README.md)。
