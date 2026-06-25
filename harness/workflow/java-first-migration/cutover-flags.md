# 迁移开关：Java-first 迁移阶段控制

> 状态：活跃
> 归属：Java-first 迁移流
> 默认值：`off`

---

## 1. 概述

本机制控制 Java-first 替代路径的执行模式。在 Python 到 Java 的渐进迁移过程中，提供四态灰度切换和安全回退能力。

核心原则：

- 默认值为 `off`，不破坏既有链路。
- 非法值 fail-fast，启动时即暴露配置错误。
- 不盲目切到 `enforce`；每个阶段升级必须有对应的验证通过。

---

## 2. 四态语义

### `off` (default)

不启用任何 Java-first 替代路径。

- 所有请求走原有链路（Python 或已稳定的 Java 路径）。
- 无任何 shadow 日志或诊断输出。
- 这是安全的默认值，适用于生产环境和未验证的部署。

### `shadow`

Java 路径参与执行但只生成对比日志，不影响输出。

- Java 替代路径被调用并生成结果。
- 结果写入对比日志（comparison log），不与原有输出合并。
- 原有链路的输出不受影响。
- 用于验证 Java 路径的正确性，收集对比数据。

### `assist`

Java 路径只参与诊断，不影响主路径。

- Java 路径提供诊断信息（如 attribution 结果、质量指标）。
- 诊断数据附加到输出中，不替代主路径结果。
- 主路径行为与 `off` 状态一致。
- 用于辅助决策和可观测性提升。

### `enforce`

Java 路径在 fixture/validation 通过后可作为候选默认。

- 前置条件：所有相关 fixture test 和 validation suite 必须通过。
- Java 路径的输出成为主输出。
- 旧链路降级为 fallback，仅在 Java 路径异常时启用。
- 这是迁移的最终目标状态，但必须是显式切换。

---

## 3. 配置来源

配置来源按优先级排列：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 显式构造器注入 | 测试或嵌入场景直接传入 `MigrationPhase` 枚举 |
| 2 | 环境变量 `FEIPI_MIGRATION_PHASE` | 部署时配置，如 `FEIPI_MIGRATION_PHASE=shadow` |
| 3 | 默认值 `off` | 未配置时的安全默认值 |

### 环境变量

```
FEIPI_MIGRATION_PHASE=off|shadow|assist|enforce
```

- 大小写不敏感。
- 前后空白自动修剪。
- 未设置或为空时回退到默认值 `off`。
- 非法值在启动时 fail-fast，抛出 `IllegalArgumentException`。

### Fail-fast 行为

非法值不会静默忽略或回退到默认值。系统启动时立即终止并报告错误：

```
非法的迁移阶段值: 'invalid_value'。允许值: off, shadow, assist, enforce
```

---

## 4. 阶段切换条件

阶段升级不是随意的，每个升级需要满足前置条件：

| 升级路径 | 前置条件 |
|----------|----------|
| `off` -> `shadow` | Java 路径代码编译通过，单元测试全绿 |
| `shadow` -> `assist` | shadow 对比日志确认 Java 输出与旧链路一致（或差异在可接受范围内） |
| `assist` -> `enforce` | 所有 fixture test 通过；validation suite 全绿；性能基准无显著退化 |
| `enforce` -> `off` (回退) | 随时可用，无需前置条件 |

---

## 5. 实现类

| 类 | 模块 | 职责 |
|-------|--------|----------------|
| `MigrationPhase` | `java/core-domain` | 四态枚举定义，`fromValue` 守卫，默认值 `OFF` |
| `MigrationPhaseConfig` | `java/application` | 配置读取（环境变量/显式值），便捷查询方法 |

### 使用示例

```java
// 从环境变量读取（生产环境）
MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment();

// 显式指定（测试场景）
MigrationPhaseConfig config = MigrationPhaseConfig.resolve("shadow");

// 检查当前状态
if (config.isShadow()) {
    // Java 路径参与执行，生成对比日志
}

if (config.isEnforce()) {
    // Java 路径作为主输出
}
```

---

## 6. 测试策略

- **枚举测试** (`MigrationPhaseTest`): 验证四态值映射、默认值、fromValue 守卫（合法/非法/大小写/空白）。
- **配置测试** (`MigrationPhaseConfigTest`): 验证环境变量解析、默认值回退、非法值 fail-fast、便捷查询方法互斥性。

---

## 7. 约束

- 默认值必须是 `off`。
- 不自动升级到更高阶段。
- 每个阶段的语义必须严格遵守，不可跳过。
- `enforce` 模式必须有 fixture/validation 通过证据。
