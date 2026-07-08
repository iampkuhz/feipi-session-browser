# Proposal: 优化 Java module 拓扑与目录层级

## Problem

当前 Java Gradle module 拆分过细且存在过渡依赖：source provider 被拆成多个小 module，`data` module 名称过泛且只服务 normalized batch，`query-api` 与 `application` 查询用例强耦合，`web` 与 `app-cli` 仍直接依赖底层实现模块。多个 module 内部也存在单包过大或目录分类不一致的问题，增加构建、迁移和长期维护成本。

## Scope

- 合并 source 实现模块：保留 `source-spi`，将 `source-json`、`source-claude`、`source-codex`、`source-qoder` 合入 `sources`。
- 合并 `query-api` 到 `application`，使查询 DTO/filter/sort/anomaly 类型由 application module 提供。
- 淘汰 `data` module，将 normalized batch protocol/runner 纳入 CLI 入口层。
- 将测试相关 module 归入 `java/tests/` 子目录：`support`、`architecture`、`contracts` 保持独立职责但不再挤占 Java 顶层 module 列表。
- 收敛 Gradle include、project dependencies、architecture boundary 配置与相关测试。
- 在不改变用户可见协议和行为的前提下，优化重点大包内部目录层级：CLI、application/query、web、index-sqlite、scan-engine 等。

## Non-goals

- 不改变 CLI 命令名、HTTP 路由、JSON/MHTML 输出协议、SQLite schema 或 normalized artifact 格式。
- 不引入 Spring/DI framework 或新的运行时框架。
- 不删除根级 `:app-cli` 历史兼容代理，除非后续单独确认。
- 不归档其他已有 OpenSpec change。

## User impact

用户运行方式、CLI 命令、Web 页面与 API 行为应保持一致。开发者面对的 Java module 数量减少，依赖边界更明确，目录按职责更易定位。

## Validation strategy

- OpenSpec layout/schema/active-change/harness 验证全部通过。
- Java module boundary 检查以 `--fail-transition` 通过，确保无残留 transition dependency。
- Gradle `check` 通过，覆盖编译、测试、Javadoc、质量门与无跳过测试检查。
