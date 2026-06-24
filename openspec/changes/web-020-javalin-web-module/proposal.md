# Proposal: WEB-020 Java Web 模块、Javalin 生命周期与 Composition Root

## 概述

建立轻量 `java/web` 模块，使用 Javalin 7 作为 HTTP 框架，Pebble 作为模板引擎，commonmark-java 作为 Markdown 解析器。

## 动机

S5 stage 需要 Java 接管 HTTP/HTML/API/serve/stop 功能。本任务是 Web 基础设施的第一步，建立 Javalin 生命周期管理和 Composition Root，为后续路由迁移提供基础。

## 范围

- 新增 `java/web` 模块
- Javalin 7 + Pebble + commonmark-java 依赖
- WebConfig 不可变配置记录
- WebServer 生命周期管理（start/stop/随机端口）
- WebCompositionRoot 显式装配（无 DI framework）
- 健康检查路由 `/healthz`
- 异常和错误 handler 注册

## 不做什么

- 不迁移具体业务路由（WEB-030 及后续任务）
- 不引入 Spring/DI framework
- 不修改 Python 代码

## 验收标准

- `./gradlew :java:web:check` 全部通过
- 模块依赖符合 ArchUnit 规则
- 空 server smoke 通过
- 中文 Javadoc 完整
