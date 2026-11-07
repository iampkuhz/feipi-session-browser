# 发布流程与工程工具契约

`java/gradle/VERSION` 是源码版本唯一真源；支持 `X.Y`、`X.Y.Z` 及现有预发布后缀。发行包根目录仍包含 `VERSION`。

预期流程是：统一质量 Gate → 四个原生构建与真实包启动 → 五包汇总并上传唯一不可变 artifact → `release-candidate` deployment → 人工批准 `github-release` → draft 上传并核验 → public。workflow 的落地与远程四平台结果须单独验证；本文不是已完成运行的证据。

`publish=false` 不创建 tag、draft 或 public Release。正式发布只消费同一 exact SHA/run/attempt 的唯一 `verified-candidate`，不从旧 run、latest 或重新构建获取资产。`release-candidate` 只登记同一 Distribution invocation 封存的 artifact ID 与 SHA/run/attempt，不再下载全套；它不证明发布者已取回资产。正式发布 job 仅在受保护的 tag Environment 人工批准后获得写权限，先拒绝缺失或陈旧的候选身份，再按该唯一 artifact ID 下载并重新校验内容。远端 tag 在 draft 写入前重新核对。发布者重下 draft 的完整资产并逐项验证后才公开；上传失败不得公开、覆盖公开 Release 或删除已有 tag。

若只重跑失败 job 导致候选仍来自旧 attempt，验收会拒绝；要产生新候选，应重跑完整工作流，不改名复用旧 artifact。正式发布留有不完整 draft 时，先人工核对 draft 身份和失败原因，再由有权限的维护者明确处置该 draft；不会自动覆盖或删除。未创建 draft 的失败可按同一身份规则重新准备候选。

## 固定 CLI

工具为 `scripts/release/release_pipeline_helpers.py`，仅使用 Python 标准库，是开发/发布工具，不进入发行包或产品运行链。以下身份参数均必填，调用方必须从可信 checkout/Actions 上下文传入，不得从待验证元数据反推：

```bash
--version <VERSION> --source-sha <40位小写commit SHA> --run-id <正整数> --run-attempt <正整数>
```

下列命令中的 `<identity>` 表示上述四个参数。

| 命令 | 输入与行为 |
|---|---|
| `prepare --dist-dir <raw> --output-dir <new> --platform <platform> [--smoke] <identity>` | 私有暂存内选取唯一固定 Gradle 文件，边复制边散列，只解包一次检查实际输出；原生 `--smoke` 同次执行本机 launcher。全成功才发布新目录；不带 `--smoke` 不产生启动凭据。 |
| `verify-archive --archive <prepared-asset> --platform <native-platform> <identity>` | 先校验同目录清单与来源；安全解包后执行当前宿主的 `bin/run` 或 `bin/run.bat`。成功自动写完整归档名后的 `.smoke.json`；重跑先删除旧凭据，失败不能保留旧成功。 |
| `verify-candidate --candidate-dir <root> <identity>` | 校验完整五包、每组输入清单、来源、归档安全/结构/版本及四个原生启动凭据；不在汇总机执行异平台二进制。 |
| `create-verified --candidate-dir <root> --output-dir <new> <identity>` | 先拒绝缺包、重复或不匹配的清单与元数据，再边复制边与输入清单比对；安全解包检查暂存的实际输出，每包一次。输入清单错误不能通过重算洗白；失败不留下可消费的输出目录。输出父目录须已存在。 |

`platform` 为 `macos-arm64`、`macos-x64`、`linux-x64`、`windows-x64` 或 `generic`（仅 prepare 可用）。原生 smoke 必须与真实宿主 CPU/OS 一致，generic 只允许在 Linux x64 准备。原始构建目录可同时含 Gradle 其他产物，但工具只选择下表确切文件，不使用通配猜测。

| 平台 | Gradle 原始文件 | 规范资产名 |
|---|---|---|
| macOS arm64 | `app-cli-runtime-VERSION.tgz` | `app-cli-VERSION-runtime-macos-arm64.tar.gz` |
| macOS x64 | `app-cli-runtime-VERSION.tgz` | `app-cli-VERSION-runtime-macos-x64.tar.gz` |
| Linux x64 | `app-cli-runtime-VERSION.tgz` | `app-cli-VERSION-runtime-linux-x64.tar.gz` |
| Windows x64 | `app-cli-runtime-VERSION.zip` | `app-cli-VERSION-runtime-windows-x64.zip` |
| Generic（Linux 唯一生成） | `app-cli-VERSION.zip` | `app-cli-VERSION-generic.zip` |

每个准备目录包含资产、`<完整资产名>.provenance.json`、`MANIFEST.SHA256`。原生验收后还包含 `<完整资产名>.smoke.json`。来源旁车严格绑定 version/source_sha/run_id/run_attempt/platform/producer_platform/filename/sha256/size，generic 的 producer_platform 必须为 `linux-x64`。启动凭据另外绑定 host_platform 及实际 version/help 输出。JSON 额外字段、重复字段或身份不一致均拒绝。

汇总输入允许两种形态：

- 扁平目录：恰好五包及其元数据、单清单；
- 一层子目录：例如四个 `dist-<platform>/`，每个含自己的清单和元数据；Linux 目录可含 native 和 generic。也可为 generic 单设一组。禁止目录内额外旁路文件、缺失元数据或重复平台。

`verified-candidate/` 是扁平目录，包含 5 个归档、5 个 `.provenance.json`、4 个 `.smoke.json`、1 个 `MANIFEST.SHA256`。下载/upload 整个目录，不能只传归档。汇总必须消费当前 exact run/attempt 的各平台 artifact。启动凭据是原生 job 的证据交换格式，不是密码签名；信任边界由 Actions artifact 的 exact run/attempt 选择及受保护 workflow 保证。合成测试可验证格式与拒绝逻辑，不能证明四平台实际运行。

退出码：成功 `0`；参数语法 `2`；prepare 失败 `1`；checksum 失败 `10`；verify-archive 解包失败 `11`、启动/输出/版本/布局失败 `13`、名称/来源/输入清单失败 `15`；verify-candidate/create-verified 任一失败 `14`。

## 构建产物边界

- 本机开发和 generic ZIP 使用原始完整依赖；generic 仍保留 SQLite 全平台 native，不是本机 runtime 包的别名。
- native `runtimeDistTar` / `runtimeDistZip` 直接消费 JAR、jlink image 与独立 launcher 输出，不先生成 `installDist` 或复制完整 `runtime-base`。`check` 的真实内嵌 runtime 测试直接使用同一 jlink image 和 launcher；`prepareRuntimeDist` 只为测试准备应用文件，不再复制 runtime。
- native SQLite JAR 保留全部类、SPI、许可证和 Maven 来源材料，只移除其他平台 native：macOS arm64/x64、Windows x64 各保留对应目录；Linux x64 同时保留 glibc/musl。未声明宿主保守保留全部；目标库缺失或 JAR 已签名时拒绝裁剪。generic JAR 不重写。四平台实际启动仍须各自环境验证。
- jlink 模块与裁剪参数保持既有合同，不删除 TLS、反射/SPI、日志、模板或导出相关依赖；不以静态引用缺失为由删除库。显式 `BUILD_TIMESTAMP`、版本、Git 身份及源码变更继续通过 Gradle 原生输入参与失效。

## 实际包验收

原生结构为 `app-cli/{VERSION,bin/run,bin/run.bat,runtime/bin/java[.exe],app/lib/*.jar}`；generic 为 `app-cli-VERSION/{VERSION,bin,lib/*.jar}`。验收不直接调用 Java 绕过 launcher，也不使用 installDist。原生 `--version` 必须包含精确版本，`--help` 必须包含 `Usage:` 以及 `scan`、`serve` 命令。

启动环境删除外部 `JAVA_HOME`、`JDK_HOME`、`JRE_HOME`、Java 注入参数及 CLASSPATH。PATH 仅提供 Unix 启动器所需的系统 `dirname` 和阻断系统 Java 的占位入口；Windows 通过系统绝对 `cmd.exe` 执行实际 `run.bat`，PATH 不包含系统 JDK。Unix 归档必须自身保留 launcher/runtime 可执行权限；工具不会 chmod 修饰坏包后宣称可运行。

安全解包先检查所有条目再写文件，拒绝绝对路径、任何 `..` 分段、反斜线、drive/UNC、大小写冲突/重复目标、文件覆盖目录，以及硬链接、符号链接和特殊文件。当前明确拒绝所有链接，包括安全内部链接；构建若引入内部 runtime 链接会阻断验收，必须先评估打包方式，不能静默放行。只接受空的非符号链接隔离目录。

## 兼容 checksum 与 drill 入口

```bash
scripts/release/generate-checksums.sh <dist-dir>
scripts/release/generate-checksums.sh <dist-dir> --verify
scripts/release/drill-upgrade-rollback.sh --candidate-dir <root> <identity>
```

checksum 薄 Bash 入口兼容 macOS Bash 3.2。清单为严格 `SHA256  SIZE  FILENAME`，归档与条目一一对应；空集合、空/畸形清单、重复/额外/缺失项、目录/链接、大小或摘要不符全部失败。生成与验证均只接受 ZIP/tar.gz 规范资产。

drill 完整复用五包验收，失败原样阻断，不再输出无实际操作的 checksum coverage 或数据安全成功。跨版本升级、回滚、Schema 迁移以及同版本备份恢复均为 `not-claimed`；本工具未执行这些操作。当前也不提供平台签名、公证能力。手动安装与恢复步骤见下文。

## 本机安装与更新

普通使用者只需下载**一个**匹配本机的 native 归档和该版本的 `MANIFEST.SHA256`，不必下载其他平台、来源/启动旁车或 Actions 整套 artifact，也不需要 Gradle、源码或系统 Java。只有没有合适的 native 包时才考虑 generic ZIP；它需要本机 Java 25，使用解压根下的 `bin/app-cli` 或 `bin\app-cli.bat`。

1. 从可信的 GitHub Release 页面获取文件，先比对清单中**该确切文件名**的 SHA-256 和字节数。macOS 可用 `shasum -a 256 <归档>`，Linux 可用 `sha256sum <归档>`，Windows 可用 `Get-FileHash -Algorithm SHA256 -LiteralPath <归档>` 与 `(Get-Item -LiteralPath <归档>).Length`。该清单用于完整性核对，不是独立签名；不要解包来源不明的文件。
2. 解压到新建的空目录，不覆盖旧安装。macOS/Linux 用 `tar -xzf <归档> -C <新目录>`，Windows 用 `Expand-Archive -LiteralPath <归档> -DestinationPath <新目录>`（不加 `-Force`）。从解压后的 `app-cli` 根运行 `./bin/run --version` 或 `& .\bin\run.bat --version`；不移动单个 launcher，也不手动给坏包补权限。
3. 用同一个 launcher 执行 `serve --host 127.0.0.1 --port 0 --index-dir <独立索引目录>`。路径含空格时加引号。打开输出的实际 URL，等自动扫描完成后检查列表和一条详情，不需先跑 `scan --full`。预览请用单独索引；`--index-dir` 只隔离索引，**不会**隔离默认会话源。用合成源做隔离验收时还须隔离 JVM `user.home`，原生 launcher 不读取 Gradle 生成脚本的 `JAVA_OPTS`；可用 JVM 的 `JAVA_TOOL_OPTIONS` 传入 `-Duser.home="绝对路径"`，并核查源路径及扫描结果。
4. 更新时先保留旧安装。正式切换前停止旧服务（前台用 Ctrl+C，等待进程退出），为整个索引目录制作独立备份，包含 SQLite 关联文件与详情产物；不要在服务仍写入时只复制数据库文件。有明确兼容性时才直接复用原索引目录。从公开 v0.4 升到 v0.5 时，保留原会话源并让新安装正常自动扫描，再检查列表和一条详情；`--no-scan` 完成 SQLite 结构迁移不等于新版已发布可见索引。
5. 新包无法启动或数据不兼容时，先停止新服务，不要让旧程序打开可能已迁移的数据库。若新版接触过原索引，把已迁移目录移到另一个位置保留，再把停服备份的独立副本恢复到原索引路径，最后让旧 launcher 指向该路径。旧索引的详情产物可能使用绝对路径，仅换恢复目录可能只能读列表、不能读正文。不要覆盖最后一份备份。已发布的 v0.4 macOS arm64 原生包无法启动 `serve`；回退该版本时可使用公开的 v0.4 generic ZIP 和 Java 25。不同版本和平台的兼容性只以实际验证范围为准。

## 本地 tag 工具与人工边界

`create-release-candidate.sh verify` 只验证本地 VERSION、干净工作区、本地 tag 唯一性及 Gradle check；不检查远程同步。仅暂存不是干净工作区。`create` 会创建 annotated tag，必须另有用户明确授权，不能因本文或自动生命周期执行。commit、push、tag、人工审批和 Release 均是独立显式操作。
