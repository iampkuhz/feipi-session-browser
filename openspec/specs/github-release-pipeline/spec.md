# GitHub Release 流程

## Requirements

### Requirement: 唯一、可追溯的候选

发行 SHALL 使用同一 workflow 的完整统一 Gate 及 macOS arm64/x64、Linux x64、Windows x64 原生 Java `check`，每平台以安全解包后的实际归档 launcher 验版本与帮助；不得用系统 Java 或 installDist 替代。四个原生归档及唯一 generic ZIP、清单、五份来源和四份启动凭据 SHALL 绑定可信 exact SHA/run/attempt，汇总只能封存一个不可变 artifact。

#### Scenario: 汇总候选

- **When** 任一平台、归档路径或结构、大小/摘要、身份或凭据不符
- **Then** SHALL 阻断候选，不能用重算输入清单、旧尝试、重新构建或部分资产替代
- **And** 暂存中只复用同一批实际校验字节，完成后才生成可消费输出

### Requirement: 保护正式发布

`publish=false` SHALL 不产生 tag、draft 或 public Release。RC SHALL 只登记本次成功封存的候选身份。正式发布 SHALL 仅从匹配 VERSION 的现有 `v*` tag 进入、由禁止管理员绕过的 `github-release` 人工审批授权，审批后按唯一 artifact ID 重验同 SHA/run/attempt 候选及远端 tag。

#### Scenario: 等待审批或上传失败

- **When** 未获人工审批、存在同名 Release，或 draft 资产验证失败
- **Then** SHALL 不创建或覆盖公开 Release，也不移动/删除已有 tag
- **And** 发布 SHALL 仅在 draft 完整下载回读、逐名逐大小和摘要验证通过后公开

### Requirement: 实际运行与升级证据

在自动扫描的原生验收中 SHALL 在启动前用实际 launcher 证实 JVM home 隔离，并显式使用独立索引。用户升级说明 SHALL 保留旧安装、停服备份整份索引，恢复使用备份的独立副本；同版本替换、跨版本迁移和恢复 SHALL 只声明实际验证范围。发布归档和清单不构成签名或公证。

#### Scenario: 版本迁移不能逆向假定

- **When** 新版已迁移索引或迁移未验证
- **Then** SHALL 不把旧版读取已迁移索引或恢复未记录历史宣称为已支持
