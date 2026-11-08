# macOS arm64 发行与本机安装

开发、构建、验证和运行只支持 **Apple Silicon（macOS arm64）**。发行包内置 Java，未签名、未公证。

## 安装与重建索引

1. 从可信 [GitHub Release](https://github.com/iampkuhz/feipi-session-browser/releases) 下载归档和 `MANIFEST.SHA256`。用 `shasum -a 256 <归档>` 和 `wc -c < <归档>` 对照清单中的摘要和字节数。
2. 停止正在运行的服务，将新归档解压到空目录，从解压后的 `app-cli` 目录运行 `./bin/run serve`，打开终端显示的地址。
3. 每个版本默认使用 `~/Library/Application Support/feipi/session-browser/<VERSION>`。新版从原始会话重建索引，不读取、迁移或删除旧版索引。若用 `--index-dir` 或 `INDEX_DIR`，为新版指定新的空目录。

## 发行流程

`java/gradle/VERSION` 是版本唯一真源。Quality 在同一个 macOS arm64 job 中选择并运行一档 Gate：一般文档和脚本变更走 incremental；Java、发布链变更及手动和 tag 运行走 full。Release 复用 Quality 的 full 路径：根 `check` 通过后只构建 `runtimeDistTar`，再解包启动并封存唯一候选。Java Quality 仅用于人工请求的专项报告。

正式发布先把包含 `VERSION` 的发行提交合入远端 `main`，再从该提交推送 `v<VERSION>` tag。Release 在构建前和人工审批后各从远端读取 `main`，确认 tag 的精确提交仍在 `main` 历史中。独立分支仍可手动运行 `publish=false` 验证候选，不创建 tag、draft 或 public Release。

`release-candidate` 只登记同 SHA/run/attempt 的 artifact ID。受保护的 `github-release` 环境批准后，发布 job 按**唯一 ID**下载并重新验证候选及远端 tag，再创建 draft、上传并回读全部资产核对名称、大小和 SHA-256，最后公开。不复用旧尝试、不重新构建，不覆盖同名 draft/Release，也不删除或移动 tag。已有不完整 draft 必须由有权限的维护者明确处置。

候选与公开资产都是四个文件：

| 文件 | 内容 |
|---|---|
| `app-cli-VERSION-runtime-macos-arm64.tar.gz` | `app-cli/{VERSION,bin/run,runtime/bin/java,app/lib/*.jar}`，内置 Java 与目标 SQLite native |
| `MANIFEST.SHA256` | 单行 `SHA256  SIZE  FILENAME` |
| `<完整归档名>.provenance.json` | 可信源码、运行身份、平台与归档大小/摘要 |
| `<完整归档名>.smoke.json` | 同一身份、真实宿主、版本/帮助、无扫描 `serve` 帮助及 JVM home 隔离证据 |

生产者从 Gradle 输出 `app-cli-runtime-VERSION.tgz` 流式复制到私有暂存并散列实际字节，不重打包。安全解包在写入前拒绝绝对路径、`..`、反斜线、重复或大小写冲突、文件遮蔽目录、链接及特殊文件。只从解包目录执行真实 `bin/run`，禁止外部 Java，且实际验证 `serve --no-scan --help` 所用 JVM home 与独立索引；不读取真实会话源。根 `check` 的运行时用例使用同一打包内容，检查 SQLite JAR 只含目标 native，再验证隔离合成源自动扫描与 Web 启动。凭据不是密码签名，信任边界是受保护 workflow 与可信 artifact ID。

## 工程入口

工具仅使用 Python 标准库，不进入产品运行链。所有候选命令均显式提供可信 `--version VERSION --source-sha SHA --run-id ID --run-attempt ATTEMPT`。

- `python3 scripts/release/release_pipeline_helpers.py prepare --dist-dir <Gradle 输出> --output-dir <新目录> <identity>`：仅在原生 macOS arm64 运行，失败不留下可消费候选。
- `python3 scripts/release/release_pipeline_helpers.py verify-candidate --candidate-dir <目录> <identity>`：复核四文件、身份、字节、安全结构及实际启动凭据。
- `scripts/release/create-release-candidate.sh verify`：只检查本地 VERSION、工作区和 tag，不构建；发布 Gate 在 GitHub 执行。只有明确授权才可创建 annotated tag、提交、推送或发布。
