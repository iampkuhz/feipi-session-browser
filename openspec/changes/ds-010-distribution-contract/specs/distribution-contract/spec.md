# Spec: Distribution Contract

## 1. 平台与架构

### 1.1 目标平台

| ID | 平台 | 架构 | 最低版本 |
|----|------|------|----------|
| PLAT-MACOS-ARM64 | macOS | arm64 | 13 (Ventura) |
| PLAT-MACOS-X64 | macOS | x64 | 13 (Ventura) |
| PLAT-LINUX-X64 | Linux | x64 | glibc 2.31 (Ubuntu 20.04) |
| PLAT-WIN-X64 | Windows | x64 | 10 (1903) |

### 1.2 运行时要求

- 不假设用户预装 JDK、Python 或 SQLite
- 使用 jlink 生成自包含 Java 25 runtime image
- SQLite 通过 Xerial JDBC 内嵌，native library 随发行包分发

## 2. 路径契约

### 2.1 默认路径

| 类型 | macOS | Linux | Windows |
|------|-------|-------|---------|
| Install | `/usr/local/lib/session-browser/` | `/usr/local/lib/session-browser/` | `%ProgramFiles%\session-browser\` |
| Data | `~/Library/Application Support/session-browser/data/` | `~/.local/share/session-browser/data/` | `%LOCALAPPDATA%\session-browser\data\` |
| Config | `~/Library/Application Support/session-browser/config/` | `~/.config/session-browser/` | `%LOCALAPPDATA%\session-browser\config\` |
| Log | `~/Library/Logs/session-browser/` | `~/.local/state/session-browser/log/` | `%LOCALAPPDATA%\session-browser\log\` |
| Cache | `~/Library/Caches/session-browser/` | `~/.cache/session-browser/` | `%LOCALAPPDATA%\session-browser\cache\` |

### 2.2 Precedence

```
CLI 参数 > 环境变量 (SB_DATA_DIR, SB_CONFIG_DIR, SB_LOG_DIR, SB_CACHE_DIR) > 平台默认
```

### 2.3 Portable 模式

安装目录含 `.portable` marker 时，所有路径相对于安装目录。

## 3. 升级与回滚

### 3.1 Schema Migration

- DB 内嵌 `schema_version` 表
- 升级前自动备份为 `.bak-<old_version>`
- migration 必须幂等且原子（事务）
- 失败时自动恢复备份，拒绝启动

### 3.2 版本兼容窗口

- 兼容 2 个连续版本（当前 + 前一版本）
- 低于窗口：拒绝访问，提示升级
- 高于当前：拒绝访问，提示更新应用

### 3.3 Rollback

- 自动失败恢复：migration 失败恢复最近备份
- 手动回滚：`--rollback` 命令
- 保留最近 2 个版本备份

## 4. 签名与 Checksum

| 平台 | 状态 | 说明 |
|------|------|------|
| macOS | 外部 BLOCKED | 需要 Apple Developer ID |
| Windows | 外部 BLOCKED | 需要 EV 代码签名证书 |
| Linux | 不需要 | 无强制签名要求 |
| 全平台 | Required | SHA-256 checksum 随发行包发布 |

## 5. 隐私

- 不发送遥测数据
- 所有数据本地存储
- 日志不记录 session 内容
