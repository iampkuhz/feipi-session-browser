# AC-020: Java Batch 生产就绪与 Python Bridge 协议适配

## 概述

建立 Python 到 Java 的进程桥，让 Python scan 流程可以调用 Java batch 来生产 normalized artifact。

## 设计决策

### 进程桥模型

- **单 JVM 约束**：一个 scan 只启动一个 JVM，bridge 复用同一进程处理所有 requests
- **不提供 Python fallback**：Java 不可用时必须明确失败
- **stdout 严格解析**：每行必须可解析为 JSON，非 NDJSON 行视为 protocol fatal

### 协议格式

NDJSON over stdin/stdout，与 `NormalizedBatchCommand` 兼容：

**Request（stdin）**:
```json
{"requestId":"req-1","sourceId":"CLAUDE_CODE","rootPath":"/path/to/session"}
```

**Response（stdout）**:
```json
{"protocol":"normalized-batch","version":"1.0"}           // 版本头
{"type":"request","requestId":"req-1","sourceId":"..."}    // 请求回显
{"requestId":"req-1","sessionKey":"...","status":"success","artifactPath":"...","contentHash":"..."}  // 结果
{"type":"end","totalRequests":N,...}                       // 结束摘要
```

### 状态映射

| Java status | artifact_path | Bridge ResultStatus |
|---|---|---|
| `success` | 有值 | `WRITTEN` |
| `success` | 空 | `UNCHANGED` |
| `skipped` | - | `UNCHANGED` |
| `error` | - | `FAILED` |

### 错误处理

| 场景 | 处理方式 |
|---|---|
| launcher 不存在 | `JavaNotAvailableError` |
| broken pipe | `BridgeError` + protocol_broken 标记 |
| 超时 | `BridgeTimeoutError` + kill 进程 |
| 取消 | `BridgeCancelledError` |
| 非 NDJSON 行 | `ProtocolFatalError` |

### Launcher 解析优先级

1. `SESSION_BROWSER_JAVA_CLI` 环境变量
2. 仓库内 `java/app-cli/build/install/app-cli/bin/app-cli`
3. PATH 中的 `session-browser-java`

## 模块清单

| 模块 | 职责 |
|---|---|
| `java_bridge.py` | Java 进程管理、NDJSON 协议、typed result |
| `normalized_batch.py` | scan 适配层、source_id 映射、结果聚合 |

## 测试覆盖

- Python bridge 单元测试：launcher 解析、协议解析、状态映射、异常路径
- Python normalized_batch 测试：source_id 映射、空请求、结果聚合
- Java 协议测试：版本头、请求回显、结束摘要、JSON 合法性

## 约束

- 不修改 forbidden scope（Java source/normalization/artifact 模块）
- 不修改 Python schema/writers
- 所有注释使用简体中文，技术术语英文
