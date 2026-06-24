# Design: WEB-020 Java Web 模块、Javalin 生命周期与 Composition Root

## 1. 模块结构

```
java/web/
├── build.gradle.kts
└── src/
    ├── main/java/com/feipi/session/browser/web/
    │   ├── package-info.java
    │   ├── WebConfig.java
    │   ├── WebServer.java
    │   └── WebCompositionRoot.java
    └── test/java/com/feipi/session/browser/web/
        ├── WebConfigTest.java
        ├── WebServerTest.java
        └── WebCompositionRootTest.java
```

## 2. 依赖选型

| 库 | 版本 | 用途 |
|---|---|---|
| Javalin | 7.0.0 | HTTP 框架（嵌入式 Jetty 12） |
| Pebble | 3.2.2 | 模板引擎（WEB-030 使用） |
| commonmark-java | 0.24.0 | Markdown 解析（WEB-070 使用） |

## 3. 关键设计决策

### 3.1 Javalin 7 路由注册方式

Javalin 7 将路由注册从 `Javalin` 实例移至 `JavalinConfig.routes`。所有 `get/post/exception/error` 调用必须在 `Javalin.create(config -> {...})` lambda 内完成。

### 3.2 Composition Root 模式

不使用 Spring/DI framework，所有依赖通过构造器注入：
- `WebCompositionRoot(QueryCompositionRoot, WebConfig)` 创建并配置 Javalin
- `WebServer(Javalin, WebConfig)` 管理生命周期

### 3.3 校验放置

- `WebConfig` 在 record compact constructor 校验 host 非空和端口范围
- 下游 Javalin 配置直接使用已验证的 int 值，不重复校验

### 3.4 健康检查路由

`GET /healthz` 返回 `{"status": "ok"}`，用于：
- 服务器 smoke 验证
- 进程存活检测
- WEB-090 serve 生命周期验证

## 4. 模块依赖

```
java:web → java:application, java:query-api, java:core-domain
java:web → Javalin, Pebble, commonmark, SLF4J
```

Web 层只依赖 application API，不直接访问 source adapter 或 JDBC。

## 5. 文件清单

| 文件 | 说明 |
|---|---|
| `WebConfig.java` | 不可变配置 record（host, port, staticPath） |
| `WebServer.java` | Javalin 生命周期管理（start/stop/actualPort） |
| `WebCompositionRoot.java` | Composition Root，注册路由和异常 handler |
| `package-info.java` | 模块级文档 |
