# GitHub Release 流程

## Requirements

### Requirement: 单一 macOS arm64 候选

发行 SHALL 仅提供 macOS arm64 自包含归档，不提供 Intel Mac、Linux、Windows 或 generic ZIP。canonical full Gate 通过后，实际 macOS arm64 宿主 SHALL 执行根 Java `check`、构建并安全解包归档，以内置 Java 通过真实 launcher 验证版本、帮助及隔离 JVM home 的无扫描 `serve` 帮助。

#### Scenario: 单一候选直接封存

- **When** macOS arm64 构建和实际归档验收通过
- **Then** 同一 job SHALL 封存唯一不可变 artifact，包含一份归档、清单、来源和启动凭据，绑定可信 exact SHA/run/attempt
- **And** 缺失或额外文件、不安全路径、结构、摘要、大小或身份不符 SHALL 阻断；不得以系统 Java、installDist、跨平台替代或旧尝试满足归档验收

### Requirement: 保护正式发布

`publish=false` SHALL 不产生 tag、draft 或 public Release。RC SHALL 只登记本次封存的候选身份。正式发布 SHALL 仅从匹配 VERSION 的现有 `v*` tag 进入，由禁止管理员绕过的 `github-release` 环境人工审批；审批后 SHALL 仅按已登记 artifact ID 直接解包到验证目录，并重新验证同 SHA/run/attempt 候选及远端 tag。

#### Scenario: 等待审批或上传失败

- **When** 未获人工审批、存在同名 Release，或 draft 资产验证失败
- **Then** SHALL 不创建或覆盖公开 Release，也不移动或删除已有 tag
- **And** 仅在完整下载回读 draft 资产并逐项核对名称、大小和摘要后 SHALL 公开

### Requirement: 实际运行与升级证据

实际自动扫描 SHALL 先用归档 launcher 证实 JVM home 隔离，并显式使用独立索引。用户升级说明 SHALL 保留旧安装、停服备份整份索引，恢复使用备份的独立副本；同版本替换、跨版本迁移和恢复只声明实际验证范围。发行归档与清单不构成签名或公证。

#### Scenario: 版本迁移不能逆向假定

- **When** 新版已迁移索引或迁移未验证
- **Then** SHALL 不把旧版读取已迁移索引或恢复未记录历史宣称为已支持
