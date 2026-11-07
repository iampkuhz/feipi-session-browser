# macOS arm64 发行与本机安装

新发行仅支持 **Apple Silicon（macOS arm64）**。不提供 Intel Mac、Linux、Windows 或 generic ZIP；历史版本资产不变。内部开发、非产品检查及发布编排仍可用其他宿主，不表示这些系统受发行支持。包未签名、未公证。

## 安装、更新与恢复

1. 从可信 [GitHub Release](https://github.com/iampkuhz/feipi-session-browser/releases) 下载 `app-cli-VERSION-runtime-macos-arm64.tar.gz` 和 `MANIFEST.SHA256`。用 `shasum -a 256 <归档>` 和 `wc -c < <归档>` 对照该文件名的摘要与字节数；清单不是签名。
2. 用 `tar -xzf <归档> -C <新建空目录>` 解包，不覆盖旧安装。从解压后的 `app-cli` 根运行 `./bin/run --version`，再运行 `./bin/run serve --host 127.0.0.1 --port 0 --index-dir <独立索引目录>`。路径含空格时加引号。用终端给出的实际 URL 检查自动扫描后的列表和一条详情。包内置 Java，不需系统 Java、Git 或 Gradle。独立索引并不隔离默认会话源。
3. 更新时保留旧安装和原会话源。先停服并等待退出，再独立备份整个索引目录（SQLite 及详情产物）。从公开 v0.4 更新时，让新安装正常扫描并检查列表、详情；`--no-scan` 的 SQLite 结构迁移不等于完成索引发布。
4. 若需恢复，先停新服务，把可能已迁移的索引移到另一位置保留，再把停服备份的独立副本放回原索引路径，最后用旧 launcher 读取它。旧索引的详情产物可能引用绝对路径，改恢复路径可能导致正文读不到。不要覆盖最后一份备份，也不要让旧版读取已迁移的索引。历史 v0.4 macOS arm64 原生包无法启动 `serve`；其备份可使用当时公开的 v0.4 generic ZIP 和 Java 25 恢复。这不是新版本的发行资产。

## 发行流程

`java/gradle/VERSION` 是源码版本唯一真源，包内仍含 `VERSION`。Release 和 CI Distribution 共用：真实 macOS arm64 的 canonical full Gate → 同平台的 Java 根 `check` + `runtimeDistTar` → 安全解包实际 launcher → 单 job 直接封存一个不可变候选。不存在跨平台 matrix、发行 generic ZIP、跨 runner 收集或重新封存。正式发布之前必须另有实际远端运行证据。

`publish=false` 不创建 tag、draft 或 public Release。Release 的 `release-candidate` deployment 仅记录同 SHA/run/attempt 封存的 artifact ID。正式发布 job 在受保护的 `github-release` 环境人工批准后，按**唯一 ID**下载到 `verified-candidate/`，重新验证候选和远端 tag；它不取旧尝试、不重新构建。随后创建 draft，逐项上传，重新下载全部资产核对名称、大小和 SHA-256，再公开。失败不得覆盖同名 draft/Release、删除或移动 tag。旧尝试或部分重跑不能复用候选；现有不完整 draft 必须由有权限的维护者明确处置。

候选与公开资产都是四个文件：

| 文件 | 内容 |
|---|---|
| `app-cli-VERSION-runtime-macos-arm64.tar.gz` | `app-cli/{VERSION,bin/run,runtime/bin/java,app/lib/*.jar}`，内置 Java 与目标 SQLite native |
| `MANIFEST.SHA256` | 单行 `SHA256  SIZE  FILENAME` |
| `<完整归档名>.provenance.json` | 可信源码、运行身份、平台与归档大小/摘要 |
| `<完整归档名>.smoke.json` | 同一身份、真实宿主、版本/帮助、无扫描 `serve` 帮助及 JVM home 隔离证据 |

生产者从 Gradle 输出 `app-cli-runtime-VERSION.tgz` 流式复制到私有暂存并散列实际字节，不重打包。安全解包在写入前拒绝绝对路径、`..`、反斜线、重复或大小写冲突、文件遮蔽目录、链接及特殊文件。只从解包目录执行真实 `bin/run`，禁止外部 Java，且实际验证 `serve --no-scan --help` 所用 JVM home 与独立索引；不读取真实会话源。根 `check` 的运行时用例还实际验证隔离合成源自动扫描与 Web 启动。凭据不是密码签名，信任边界是受保护 workflow 与可信 artifact ID。

## 工程入口

工具仅使用 Python 标准库，不进入产品运行链。所有候选命令均显式提供可信 `--version VERSION --source-sha SHA --run-id ID --run-attempt ATTEMPT`。

- `python3 scripts/release/release_pipeline_helpers.py prepare --dist-dir <Gradle 输出> --output-dir <新目录> <identity>`：仅在原生 macOS arm64 运行，失败不留下可消费候选。
- `python3 scripts/release/release_pipeline_helpers.py verify-candidate --candidate-dir <目录> <identity>`：复核四文件、身份、字节、安全结构及实际启动凭据；不在非 macOS 宿主运行归档。
- `scripts/release/generate-checksums.sh <目录> [--verify]`：校验 tar.gz 清单，兼容 macOS Bash 3.2。正式候选始终使用单归档清单。
- `scripts/release/drill-upgrade-rollback.sh --candidate-dir <目录> <identity>`：只复用候选复核，不执行升级、备份或回滚。
- `scripts/release/create-release-candidate.sh verify`：检查本地 VERSION、干净工作区、tag 唯一性和 Gradle check，不核远端。只有明确授权才可创建 annotated tag、提交、推送或发布。
