# SI-050 Tasks

## Task SI-050: Java Full Scan Engine

- **状态**: DONE
- **模块**: `java/scan-engine`
- **实际文件**:
  - `java/scan-engine/build.gradle.kts`
  - `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/FullScanEngine.java`
  - `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/ScanConfig.java`
  - `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/ScanSummary.java`
  - `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/ScanIssue.java`
  - `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/ScanLogManager.java`
  - `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/package-info.java`
  - 测试: `FullScanEngineTest`, `ScanConfigTest`, `ScanSummaryTest`, `ScanIssueTest`, `ScanLogManagerTest`
- **更新文件**:
  - `settings.gradle.kts` — 添加 `java:scan-engine`
  - `java/app-cli/build.gradle.kts` — 添加 scan-engine 依赖
  - `java/contract-tests/build.gradle.kts` — 添加 scan-engine 依赖
  - `config/api-snapshots/java-public-api.txt` — 更新公开 API 基线
