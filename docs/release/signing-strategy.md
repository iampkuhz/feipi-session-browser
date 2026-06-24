# 签名与 Notarization 策略

本文档描述 Feipi Session Browser 各平台代码签名和公证策略。

## 平台矩阵

| 平台 | 签名方式 | Notarize/Gateway | Secret 要求 |
|---|---|---|---|
| macOS arm64 | `codesign` + Developer ID | `notarytool` + `stapler` | `APPLE_CERTIFICATE_P12`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_TEAM_ID` |
| macOS x64 | `codesign` + Developer ID | `notarytool` + `stapler` | 同上 |
| Linux x64 | 无原生签名机制 | 通过 checksum (SHA-256) 验证完整性 | 无 |
| Windows x64 | `signtool` + EV/OV 证书 | RFC 3161 timestamp | `WIN_CERTIFICATE_PFX`, `WIN_CERTIFICATE_PASSWORD` |

## Fail closed 原则

签名 secret 缺失时 CI 不阻塞构建，但：

- macOS 签名步骤跳过，产物标记 `BLOCKED_EXTERNAL`。
- Windows 签名步骤跳过，产物标记 `BLOCKED_EXTERNAL`。
- Linux 通过 checksum manifest 提供完整性保证，无需签名。
- 正式发布（`v*` tag）前必须配置全部签名 secret。

## macOS 签名流程

1. **证书导入**：CI 从 `APPLE_CERTIFICATE_P12` (base64) 解码导入临时 keychain。
2. **签名目标**：
   - `jlink-image/bin/java`（runtime 可执行文件）
   - `install/app-cli/bin/app-cli`（CLI launcher）
3. **公证（Notarize）**：仅 tag 触发，使用 `xcrun notarytool submit --wait`。
4. **Staple**：公证通过后执行 `xcrun stapler staple` 将 ticket 附加到 archive。

### 所需 Secret

| Secret | 来源 | 说明 |
|---|---|---|
| `APPLE_CERTIFICATE_P12` | Apple Developer | Developer ID 证书 `.p12`，base64 编码 |
| `APPLE_CERTIFICATE_PASSWORD` | 导出时设置 | `.p12` 解压密码 |
| `APPLE_TEAM_ID` | Apple Developer | Team ID（10 字符） |
| `APPLE_NOTARY_USER` | Apple Developer | Notarization 专用 Apple ID |
| `APPLE_NOTARY_PASSWORD` | Apple Developer | App-specific password |

## Windows 签名流程

1. **证书导入**：CI 从 `WIN_CERTIFICATE_PFX` (base64) 解码到临时文件。
2. **签名目标**：
   - `app-cli.bat` 包装的 `java.exe`（如适用）
   - `jlink-image/bin/java.exe`
3. **Timestamp**：使用 RFC 3161（`http://timestamp.digicert.com`）。
4. **清理**：签名后删除临时证书文件。

### 所需 Secret

| Secret | 来源 | 说明 |
|---|---|---|
| `WIN_CERTIFICATE_PFX` | CA 提供商 | EV/OV 代码签名证书，base64 编码 |
| `WIN_CERTIFICATE_PASSWORD` | 申请时设置 | `.pfx` 解压密码 |

## Linux 完整性保证

Linux 无原生代码签名机制，通过以下方式保证供应链安全：

- **SHA-256 checksum manifest**：每个发行包附带 `MANIFEST.SHA256`。
- **Gradle Wrapper 验证**：`gradle/actions/wrapper-validation` 校验 wrapper JAR。
- **依赖锁定**：`dependencyLocking { lockAllConfigurations() }` 防止依赖漂移。

## 供应链安全

- **不自动接受依赖 checksum**：CI 不缓存或信任上游 dependency hash，每次由 Gradle 重新验证。
- **Secret 最小化**：签名 secret 仅存在于 GitHub Secrets，不进入日志或 artifact。
- **Artifact retention**：
  - 测试结果：7 天
  - Distribution：14 天
  - Checksum manifest：30 天
- **权限最小化**：CI workflow 默认 `contents: read`，不请求额外权限。

## 校验放置

| 校验 | Trust boundary | 位置 |
|---|---|---|
| Gradle wrapper JAR 完整性 | 工具链入口 | CI `validate Gradle Wrapper` step |
| 依赖依赖锁定一致性 | 构建入口 | `build.gradle.kts` `dependencyLocking` |
| Distribution SHA-256 | 发布边界 | `scripts/release/generate-checksums.sh` |
| 消费者验证 | 下载后 | `generate-checksums.sh --verify` |
