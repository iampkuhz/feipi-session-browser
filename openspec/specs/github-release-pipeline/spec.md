# GitHub Release 流程

## Requirements

### Requirement: 单一 macOS arm64 候选

发行 SHALL 仅提供 macOS arm64 自包含归档，不提供 Intel Mac、Linux、Windows 或 generic ZIP。canonical full Gate SHALL 对同一提交执行 Java 根 `check`。Gate 通过后，实际 macOS arm64 宿主 SHALL 构建并安全解包归档，以内置 Java 通过真实 launcher 验证版本、帮助及隔离 JVM home 的无扫描 `serve` 帮助。

发行归档 SHALL 只生成原生 `bin/run`，其 SQLite JDBC JAR SHALL 保留 JDBC 类、SPI、许可及唯一的 macOS arm64 native。根 `check` 使用同一打包内容验证实际内嵌 JVM 和 SQLite 自动扫描，不依赖合成多平台打包。

统一 Quality SHALL 在同一 macOS arm64 job 内选择并执行一档 Gate，并在首次执行 Gradle 前验证 Wrapper。Java 或发布链变更、手动运行和 tag SHALL 走 full；其他有可信 diff 基线的运行 SHALL 走 incremental。Release SHALL 复用 Quality 的 full 路径；full Gate 通过后仅运行 `runtimeDistTar`，不再执行 Java `check`。独立 Java Quality workflow 只按需生成专项报告。

#### Scenario: 单一候选直接封存

- **When** macOS arm64 构建和实际归档验收通过
- **Then** 同一 job SHALL 封存唯一不可变 artifact，包含一份归档、清单、来源和启动凭据，绑定可信 exact SHA/run/attempt
- **And** 缺失或额外文件、不安全路径、结构、摘要、大小或身份不符 SHALL 阻断；不得以系统 Java、installDist、跨平台替代或旧尝试满足归档验收

### Requirement: 保护正式发布

`publish=false` SHALL 不产生 tag、draft 或 public Release，允许独立分支验证。RC SHALL 只登记本次封存的候选身份。正式发布 SHALL 仅从匹配 VERSION 的现有 `v*` tag 进入，由禁止管理员绕过的 `github-release` 环境人工审批。构建前及审批后 SHALL 分别从远端读取 `main`，验证 tag 指向的精确提交是 `main` 的当前提交或其祖先；无法验证 SHALL 阻断发布。审批后 SHALL 仅按已登记 artifact ID 直接解包到验证目录，并重新验证同 SHA/run/attempt 候选及远端 tag。

#### Scenario: 发行提交不在远端 main

- **When** 正式 tag 指向尚未合入 `main` 的提交，或审批后该提交不再位于 `main` 历史中
- **Then** SHALL 拒绝继续；不创建 draft 或 public Release

#### Scenario: 等待审批或上传失败

- **When** 未获人工审批、存在同名 Release，或 draft 资产验证失败
- **Then** SHALL 不创建或覆盖公开 Release，也不移动或删除已有 tag
- **And** 仅在完整下载回读 draft 资产并逐项核对名称、大小和摘要后 SHALL 公开

### Requirement: 实际运行与索引重建

开发、构建、验证和运行 SHALL 只支持 Apple Silicon macOS。实际自动扫描 SHALL 使用隔离 JVM home 和独立索引。每个发布版本 SHALL 默认使用独立索引目录，由新版本扫描原始会话重建；不得迁移、回滚、读取或覆盖旧版索引。允许同版本增量更新。发行归档与清单不构成签名或公证。

#### Scenario: 新版启动

- **When** 启动不同于现有索引版本的新版本
- **Then** SHALL 在默认版本目录从原始会话重建；显式指向旧版索引时拒绝，不修改旧索引
