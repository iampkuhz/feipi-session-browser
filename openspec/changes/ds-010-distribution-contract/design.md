# Design: 发行目标、平台、升级与回滚契约

## 1. 概述

本 design 冻结 S6 Distribution + Operations stage 的全部发行契约。覆盖：目标平台与架构、发行包形态、安装/数据/配置/日志/缓存路径与 precedence、DB backup/migration/rollback 与版本兼容窗口、签名/notarization 策略。

## 2. 目标平台与架构

### 2.1 正式发行目标

| 契约 ID | OS | 架构 | 标识符 |
|---------|----|----|--------|
| PLAT-MACOS-ARM64 | macOS 13+ (Ventura) | arm64 (Apple Silicon) | `darwin-aarch64` |
| PLAT-MACOS-X64 | macOS 13+ (Ventura) | x64 (Intel) | `darwin-x64` |
| PLAT-LINUX-X64 | Linux (glibc 2.31+, Ubuntu 20.04+) | x64 | `linux-x64` |
| PLAT-WIN-X64 | Windows 10+ (1903) | x64 | `win-x64` |

### 2.2 运行时

- Java 25 LTS，使用 `jlink` 生成自包含 runtime image
- 不假设用户预装 JDK/JRE
- 不假设用户预装 Python
- SQLite 通过 Xerial JDBC 内嵌，native library 由 jlink 打包

### 2.3 构建环境

| 平台 | CI Runner | JDK |
|------|-----------|-----|
| macOS arm64 | GitHub Actions `macos-14` (arm64) | Eclipse Temurin 25 |
| macOS x64 | GitHub Actions `macos-13` (x64) | Eclipse Temurin 25 |
| Linux x64 | GitHub Actions `ubuntu-22.04` | Eclipse Temurin 25 |
| Windows x64 | GitHub Actions `windows-2022` | Eclipse Temurin 25 |

## 3. 发行包形态

### 3.1 包格式

| 契约 ID | 平台 | 格式 | 内容 |
|---------|------|------|------|
| PKG-MACOS-ARM64 | macOS arm64 | `.tar.gz` | jlink image + launcher + license |
| PKG-MACOS-X64 | macOS x64 | `.tar.gz` | jlink image + launcher + license |
| PKG-LINUX-X64 | Linux x64 | `.tar.gz` | jlink image + launcher + license |
| PKG-WIN-X64 | Windows x64 | `.zip` | jlink image + launcher + license |

### 3.2 发行包目录结构

```
session-browser/
  bin/
    session-browser          # Unix launcher (bash)
    session-browser.bat      # Windows launcher (cmd)
  lib/
    session-browser.jar      # 主 application jar
    sqlite-jdbc-*.jar        # SQLite JDBC (含 native library)
    jackson-*.jar            # JSON 处理
    javalin-*.jar            # HTTP server
    pebble-*.jar             # Template engine
    slf4j-*.jar              # Logging
    ...                      # 其他运行时依赖
  runtime/                   # jlink 生成的 self-contained JRE
    bin/java
    lib/...
    conf/...
  LICENSE
  VERSION
```

### 3.3 jlink Runtime Image 约束

| 约束 | 说明 |
|------|------|
| 不包含 GUI 模块 | 排除 `java.desktop` 等 GUI 模块 |
| 压缩 | `--compress=zip-6` |
| 去除调试信息 | `--no-header-files --no-man-pages` |
| 仅需要模块 | 基于 `jdeps` 分析确定模块列表 |
| SQLite native library | 从 Xerial jar 提取 `.dylib`/`.so`/`.dll` 放入 `runtime/lib/` |

## 4. 路径契约

### 4.1 路径分类与默认值

| 契约 ID | 类型 | macOS | Linux | Windows |
|---------|------|-------|-------|---------|
| PATH-INSTALL | 安装目录 (只读) | `/usr/local/lib/session-browser/` | `/usr/local/lib/session-browser/` | `%ProgramFiles%\session-browser\` |
| PATH-DATA | 用户数据 (读写) | `~/Library/Application Support/session-browser/data/` | `~/.local/share/session-browser/data/` | `%LOCALAPPDATA%\session-browser\data\` |
| PATH-CONFIG | 用户配置 (读写) | `~/Library/Application Support/session-browser/config/` | `~/.config/session-browser/` | `%LOCALAPPDATA%\session-browser\config\` |
| PATH-LOG | 日志 (读写) | `~/Library/Logs/session-browser/` | `~/.local/state/session-browser/log/` | `%LOCALAPPDATA%\session-browser\log\` |
| PATH-CACHE | 缓存 (读写, 可删除) | `~/Library/Caches/session-browser/` | `~/.cache/session-browser/` | `%LOCALAPPDATA%\session-browser\cache\` |

### 4.2 路径 Precedence

```
CLI 参数 (--data-dir, --config-dir, --log-dir, --cache-dir)
  > 环境变量 (SB_DATA_DIR, SB_CONFIG_DIR, SB_LOG_DIR, SB_CACHE_DIR)
  > 平台默认值
```

| 契约 ID | 环境变量 | 说明 |
|---------|----------|------|
| ENV-DATA | `SB_DATA_DIR` | 覆盖 data 目录 |
| ENV-CONFIG | `SB_CONFIG_DIR` | 覆盖 config 目录 |
| ENV-LOG | `SB_LOG_DIR` | 覆盖 log 目录 |
| ENV-CACHE | `SB_CACHE_DIR` | 覆盖 cache 目录 |

### 4.3 Portable 模式

当安装目录包含 `.portable` marker 文件时，所有路径相对于安装目录：

```
<install-dir>/
  .portable
  data/
  config/
  log/
  cache/
```

### 4.4 目录内布局

```
data/
  session-browser.db          # 主 SQLite 数据库
  session-browser.db.backup   # 最近一次升级前备份
  session-browser.db.bak-<version>  # 版本化备份
  indexes/                    # 扫描索引 (可重建)

config/
  config.properties           # 用户配置 (可选)

log/
  session-browser.log         # 当前日志
  session-browser.log.1       # 滚动日志 (最多 5 个)

cache/
  scan/                       # 扫描缓存
  web/                        # Web 静态资源缓存
```

## 5. DB Backup、Migration 与 Rollback

### 5.1 SQLite 版本管理

| 契约 ID | 说明 |
|---------|------|
| DB-VERSION | SQLite DB 内嵌 `schema_version` 表，记录当前 schema 版本 |
| DB-COMPAT-WINDOW | 兼容窗口：当前版本和前一版本（2 个连续版本） |
| DB-REJECT-OLD | 低于兼容窗口的旧版本启动时拒绝访问，提示先升级 |
| DB-REJECT-NEW | 高于当前版本的 DB 拒绝访问，提示升级到支持该版本的应用 |

### 5.2 Schema Migration 流程

```
应用启动
  > 读取 DB schema_version
  > 比较当前应用期望版本
  > 如果版本相同：正常使用
  > 如果需要升级：
    1. 备份当前 DB 为 session-browser.db.bak-<old_version>
    2. 按顺序执行 migration SQL
    3. 更新 schema_version
    4. 验证迁移后数据完整性
  > 如果 migration 失败：
    1. 恢复备份
    2. 记录错误日志
    3. 拒绝启动（数据安全第一）
```

### 5.3 Rollback 策略

| 契约 ID | 场景 | 行为 |
|---------|------|------|
| RB-AUTO-FAIL | migration 失败 | 自动恢复最近备份，拒绝启动 |
| RB-MANUAL | 用户回滚到旧版本 | 使用 `--rollback` 命令从备份恢复 |
| RB-BACKUP-KEEP | 升级成功 | 保留最近 2 个版本备份 |
| RB-BACKUP-CLEAN | 超过 2 个备份 | 自动清理最旧备份 |

### 5.4 Migration 安全约束

- migration 必须是幂等的（可重入）
- migration 使用事务，保证原子性
- 不删除用户数据，只做 additive schema 变更
- destructive 变更必须先备份

## 6. 签名与 Notarization

### 6.1 状态判定

| 契约 ID | 平台 | 状态 | 说明 |
|---------|------|------|------|
| SIGN-MACOS | macOS | 外部 BLOCKED | 需要 Apple Developer ID ($99/年) 和 notarization 服务 |
| SIGN-WIN | Windows | 外部 BLOCKED | 需要 EV 代码签名证书 ($200-400/年) |
| SIGN-LINUX | Linux | 不需要 | Linux 无强制签名要求 |
| CHECKSUM | 全平台 | Required | SHA-256 checksum 文件随发行包发布 |

### 6.2 Checksum 契约

| 契约 ID | 文件 | 格式 |
|---------|------|------|
| CKSUM-SHA256 | `session-browser-<version>-<platform>.sha256` | `<sha256>  <filename>\n` |
| CKSUM-VERIFY | 用户手动 | `sha256sum -c <checksum-file>` |

### 6.3 供应链安全

| 契约 ID | 措施 | 说明 |
|---------|------|------|
| SUPPLY-DEPS | 依赖锁定 | Gradle dependency lock (`gradle.lockfile`) |
| SUPPLY-JLINK | jlink 可重现 | 同一 JDK 版本 + 相同模块 = 相同输出 |
| SUPPLY-SBOM | 未来考虑 | 暂不强制 SBOM，但保留扩展点 |

## 7. Validation Placement

| 校验条件 | 唯一主要位置 | 下游行为 |
|----------|-------------|----------|
| 安装目录只读性 | launcher/config boundary | application 只使用 resolved paths |
| 路径合法性 (无 `..` 穿越) | launcher/config boundary | application 信任 resolved paths |
| 环境变量格式 | CLI/config adapter | typed config 后不重复解析 |
| CLI 参数格式 | CLI adapter | typed config 后不重复解析 |
| DB schema_version 读取 | migration manager | repository 使用已验证 schema |
| DB backup 完整性 | migration manager | rollback 信任备份 |
| DB 版本兼容窗口 | migration manager | application 拒绝不兼容 DB |
| migration 事务原子性 | migration manager (SQLite transaction) | DB 约束保证数据一致性 |
| checksum 验证 | CI/release workflow | 用户手动验证 |
| jlink image 完整性 | launcher (启动时检查 java 可执行) | application 信任运行时 |
| SQLite native library 加载 | source adapter/SQLite JDBC | application 信任已加载 driver |

## 8. 重复校验审计

| 条件 | 出现位置 | 判断 |
|------|----------|------|
| 路径存在性检查 | launcher (启动前), migration manager (DB 操作前) | 不同 trust boundary; launcher 快速失败, migration 数据安全 |
| 版本格式校验 | CLI (`--version`), VERSION 文件读取, DB schema_version | CLI 是输入校验, VERSION 是发行包完整性, DB 是数据完整性; 不同 boundary |
| 配置文件解析 | config adapter (启动时) | 单一入口, 下游使用 typed config |

## 9. S6 Task 归属与路径契约

| S6 Task | 覆盖契约 | 路径类型 |
|---------|----------|----------|
| DS-010 | 全部路径/平台/升级/签名契约冻结 | PLAN |
| DS-020 | PKG-*, jlink runtime image 构建 | PATH-INSTALL 内部 |
| DS-030 | SQLite native library 打包与加载 | PATH-INSTALL/lib/ |
| DS-040 | PATH-DATA/CONFIG/LOG/CACHE, PATH-INSTALL 只读, portable 模式 | 全部路径 |
| DS-050 | DB-VERSION, DB-COMPAT-WINDOW, RB-*, migration 流程 | PATH-DATA |
| DS-060 | launcher (bin/session-browser, bin/session-browser.bat) | PATH-INSTALL/bin/ |
| DS-065 | 发行体积、启动、内存与依赖精简优化 | 全部 |
| DS-070 | portable/clean machine/fault fixture 只读门禁 | 全部路径 |
| DS-080 | CKSUM-*, SIGN-*, SUPPLY-* | 发行产物 |
| DS-090 | release workflow, upgrade/rollback drill | 全部 |
| DS-100 | S6 stage closeout, ownership 收口 | 全部 |

## 10. 隐私与数据边界

| 契约 ID | 说明 |
|---------|------|
| PRIV-NO-TELEMETRY | 不发送任何遥测数据到外部服务 |
| PRIV-LOCAL-ONLY | 所有数据存储在本地 PATH-DATA |
| PRIV-LOG-REDACT | 日志中不记录 session 内容，只记录操作元数据 |
| PRIV-DB-ENCRYPT | 暂不加密 DB（本地工具，数据在用户设备上） |
