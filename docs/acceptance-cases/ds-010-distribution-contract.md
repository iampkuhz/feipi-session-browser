# DS-010 发行契约验收合同

## 1. 平台覆盖

| 验收 ID | 平台 | 验收标准 |
|---------|------|----------|
| AC-PLAT-MACOS-ARM64 | macOS arm64 | jlink image 在 macOS 13+ arm64 可启动、serve、scan |
| AC-PLAT-MACOS-X64 | macOS x64 | jlink image 在 macOS 13+ x64 可启动、serve、scan |
| AC-PLAT-LINUX-X64 | Linux x64 | jlink image 在 Ubuntu 20.04+ x64 可启动、serve、scan |
| AC-PLAT-WIN-X64 | Windows x64 | jlink image 在 Windows 10+ x64 可启动、serve、scan |

## 2. 路径验收

| 验收 ID | 场景 | 验收标准 |
|---------|------|----------|
| AC-PATH-DEFAULT | 无参数启动 | 使用平台默认路径创建 data/config/log/cache 目录 |
| AC-PATH-ENV | 设置 SB_DATA_DIR 环境变量 | data 目录使用环境变量值 |
| AC-PATH-CLI | 使用 --data-dir 参数 | data 目录使用 CLI 参数值 |
| AC-PATH-PRECEDENCE | 同时设置 CLI 和环境变量 | CLI 参数优先 |
| AC-PATH-PORTABLE | 安装目录含 .portable | 所有路径相对于安装目录 |
| AC-PATH-READONLY | 安装目录只读 | 应用在 install 目录只写 log/cache 到用户目录 |

## 3. DB 验收

| 验收 ID | 场景 | 验收标准 |
|---------|------|----------|
| AC-DB-UPGRADE | 旧版本 DB 升级 | 自动备份后 migration 成功 |
| AC-DB-MIGRATION-FAIL | migration 失败 | 自动恢复备份，拒绝启动 |
| AC-DB-REJECT-OLD | 低于兼容窗口 | 拒绝访问，提示升级 |
| AC-DB-REJECT-NEW | DB 版本高于应用 | 拒绝访问，提示更新 |
| AC-DB-ROLLBACK | 手动回滚 | `--rollback` 恢复备份成功 |
| AC-DB-BACKUP-CLEAN | 超过 2 个备份 | 自动清理最旧备份 |

## 4. 签名与 Checksum 验收

| 验收 ID | 场景 | 验收标准 |
|---------|------|----------|
| AC-CKSUM-SHA256 | 发行包 checksum | SHA-256 文件可用 `sha256sum -c` 验证 |
| AC-SIGN-MACOS | macOS 签名 | BLOCKED (需要 Apple Developer ID) |
| AC-SIGN-WIN | Windows 签名 | BLOCKED (需要 EV 证书) |

## 5. 隐私验收

| 验收 ID | 场景 | 验收标准 |
|---------|------|----------|
| AC-PRIV-NO-TELEMETRY | 网络监控 | 无外部网络连接 |
| AC-PRIV-LOG-REDACT | 日志审查 | 日志不含 session 内容 |
