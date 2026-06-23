# SI-100: Java Scan CLI、Shell 路由与用户行为 Cutover

## 动机

S3 stage 第十个任务。SI-090 完成了故障注入测试，Java scan engine 全链路已通过验证。
现在需要在原 `scan` 命令名下将路由切换到 Java 实现，实现用户行为 cutover。

## 范围

- 更新 `java/app-cli/.../ScanCommand.java` — 实现完整的 scan 子命令，支持 --full/--incremental/--agent/--force 选项
- 更新 `scripts/session-browser.sh` — `scan` 子命令路由到 Java launcher
- 复用 `java/scan-engine` 已有的 FullScanEngine、IncrementalScanEngine、ScanLock 等组件
- 复用 `java/index-sqlite` 的 ConnectionFactory 创建 SQLite 连接
- 复用 `java/source-*` 适配器通过 SourceAdapter SPI 发现源数据
- 新增 ScanCommand 契约测试
- 不修改 Python scan 路径或 web 模块

## 约束

- 用户可见命令无 java/python 后缀
- scan 不启动 Python
- 失败输出中文且 exit code 稳定（0=成功, 1=错误, 2=锁冲突）
- 默认非交互：冲突不提示 stdin，使用明确 flag/exit code
- Shell 定位发行 launcher，不运行时 Gradle build
- 路径含空格、任意 cwd 兼容（由 installDist 产物保证）
