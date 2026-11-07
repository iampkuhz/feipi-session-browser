---
name: feipi-java-feature-dev
disable-model-invocation: true
description: 用于本仓库 Java/Gradle/API/CLI 功能研发的最小上下文执行规则；纯 UI、纯文档、纯 OpenSpec 编排不要使用。
---

# Java 功能研发

先定位目标类和相邻测试。仅在模块依赖、API 或构建配置变化时，查看 `java/settings.gradle.kts` 的映射、目标模块的 dependencies 和 `java/gradle/config/architecture/java-modules.yaml` 的相关条目。不要扫描整个模块。

- 保持分层：API/CLI 不读底层存储，Service 不写模板，Repo 不渲染。复用现有 DTO/Mapper/DAO/Repo/Service 命名与边界。
- Java 源码规约见 `openspec/specs/java-code-conciseness/spec.md`，按改动加载有关条目。
- 开发中直接运行相邻测试，例如 `./java/gradlew -p java :java:<module>:test --tests '*<TestClass>'`。改动跨模块才按影响扩展，不把 root `check` 当作每次编辑反馈。
- 提交或交接按 `AGENTS.md`，说明验证范围和模块依赖变化。最终根 `check` 已覆盖的测试不重复运行。
