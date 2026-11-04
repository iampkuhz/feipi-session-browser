# 发布流程与工程工具契约

`java/gradle/VERSION` 是源码版本唯一真源；支持 `X.Y`、`X.Y.Z` 及现有预发布后缀。发行包根目录仍包含 `VERSION`。

预期流程是：统一质量 Gate → 四个原生构建与真实包启动 → 五包汇总 → `release-candidate` deployment → 人工批准 `github-release` → draft 上传并核验 → public。workflow 的落地与远程四平台结果须单独验证；本文不是已完成运行的证据。

`publish=false` 不创建 tag、draft 或 public Release。正式发布只消费同一 exact SHA/run/attempt 的唯一 `verified-candidate`，不从旧 run、latest 或重新构建获取资产。发布 job 应仅在受保护的 tag Environment 人工批准后获得写权限，先核验 draft 完整资产，再公开；上传失败不得公开、覆盖公开 Release 或删除已有 tag。

## 固定 CLI

工具为 `scripts/release/release_pipeline_helpers.py`，仅使用 Python 标准库，是开发/发布工具，不进入发行包或产品运行链。以下身份参数均必填，调用方必须从可信 checkout/Actions 上下文传入，不得从待验证元数据反推：

```bash
--version <VERSION> --source-sha <40位小写commit SHA> --run-id <正整数> --run-attempt <正整数>
```

下列命令中的 `<identity>` 表示上述四个参数。

| 命令 | 输入与行为 |
|---|---|
| `prepare --dist-dir <raw> --output-dir <new> --platform <platform> <identity>` | 选取唯一固定 Gradle 文件，安全检查并复制为规范名；输出目录不得已存在。只生成资产、来源旁车及清单，不宣称启动成功。 |
| `verify-archive --archive <prepared-asset> --platform <native-platform> <identity>` | 先校验同目录清单与来源；安全解包后执行当前宿主的 `bin/run` 或 `bin/run.bat`。成功自动写完整归档名后的 `.smoke.json`；重跑先删除旧凭据，失败不能保留旧成功。 |
| `verify-candidate --candidate-dir <root> <identity>` | 校验完整五包、每组输入清单、来源、归档安全/结构/版本及四个原生启动凭据；不在汇总机执行异平台二进制。 |
| `create-verified --candidate-dir <root> --output-dir <new> <identity>` | 先执行同样的严格输入验收，再复制已有资产/旁车到新目录，生成汇总清单并重验输出。输入清单错误不能通过重算洗白；失败不留下输出目录。输出父目录须已存在。 |

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

drill 完整复用五包验收，失败原样阻断，不再输出无实际操作的 checksum coverage 或数据安全成功。跨版本升级、回滚、Schema 迁移以及同版本备份恢复均为 `not-claimed`；本工具未执行这些操作。当前也不提供平台签名、公证能力。

## 本地 tag 工具与人工边界

`create-release-candidate.sh verify` 只验证本地 VERSION、干净工作区、本地 tag 唯一性及 Gradle check；不检查远程同步。仅暂存不是干净工作区。`create` 会创建 annotated tag，必须另有用户明确授权，不能因本文或自动生命周期执行。commit、push、tag、人工审批和 Release 均是独立显式操作。
