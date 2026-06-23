# SI-100 Tasks

## Task SI-100: Java Scan CLI、Shell 路由与用户行为 Cutover

- **状态**: DONE
- **模块**: `java/app-cli`, `scripts/session-browser.sh`
- **实际文件**:
  - `java/app-cli/src/main/java/com/feipi/session/browser/cli/ScanCommand.java`
  - `java/app-cli/src/test/java/com/feipi/session/browser/cli/ScanCommandTest.java`
  - `java/app-cli/build.gradle.kts`
  - `scripts/session-browser.sh`
- **更新文件**:
  - `java/app-cli/build.gradle.kts` — 添加 index-sqlite、sqlite-jdbc、slf4j 依赖
- **OpenSpec change**: `openspec/changes/si-100-java-scan-cli-cutover/`
  - `proposal.md`
  - `design.md`
  - `tasks.md`
