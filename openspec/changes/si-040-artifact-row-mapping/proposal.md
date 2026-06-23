# SI-040 Proposal: Normalized Artifact 到 Index Row 映射与不变量

## 背景

SI-030 完成了 SQLite 连接运行时基础设施。SI-040 需要把归一化制品映射为 index 行数据。

## 变更内容

### 新增类型

- `SessionRow` — sessions 表类型化行 record
- `SessionArtifactRow` — session_artifacts 表类型化行 record
- `ArtifactRowMapper` — 归一化制品到 index row 的唯一映射器

### 修改

- `index-sqlite/build.gradle.kts` — 添加 `core-domain` 依赖
- `package-info.java` — 更新模块文档，添加行映射节

### 依赖变更

| 来源 | 目标 | 类型 |
|------|------|------|
| index-sqlite | core-domain | implementation (新增) |

## 影响范围

- `java/index-sqlite/**` — 新增 3 个 public type + 测试
- `config/api-snapshots/**` — API 基线更新
