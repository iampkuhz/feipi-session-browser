# 开发与仓库结构

安装和日常使用见[首页](../../README.md)。本页只面向修改代码、运行检查的贡献者。

## 开发环境与验证

开发只支持 Apple Silicon macOS 和原生 JDK 25；Gradle Wrapper 和 Gate 自动发现 JDK，错误的显式 `JAVA_HOME` 不回退。排查时运行
`./java/gradlew -p java --version`，确认 Launcher JVM 和 Daemon JVM 均为 25；显式设置时也可运行
`"$JAVA_HOME/bin/java" -version`。完整发现逻辑见 `scripts/harness/java_env.sh`。

```bash
# 首次或锁定环境变化时，从仓库根执行
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv sync --project scripts --frozen --extra dev
./scripts/session-browser.sh deps
```

## 日常小改

定位改动和相邻测试后，选一个能证明效果的命令。这里是**反馈**，不扫整个脏工作区、不生成交付 receipt。

| 改动 | 就地反馈（从仓库根运行） |
|---|---|
| 普通 Markdown | `git diff HEAD --check -- <path>`；新文件直接审阅，修改链接时核对目标 |
| 局部 Java | `./java/gradlew -p java :java:<module>:test --tests '*<TestClass>'` |
| 页面样式/交互 | `npm --prefix java/tests/playwright test -- <相邻-spec>`；共享样式选受影响的多个 spec。结构修改可选相邻 Web 资源契约测试 |
| 工程脚本 | Shell 用 `bash -n -- <path>`，行为改动跑相邻测试。Python 用 `.local/python/venv/bin/python -m pytest -c scripts/pyproject.toml --rootdir . -n 0 <test-path>`；无运行行为时可用 Ruff 定向检查 |
| 共享契约 | OpenSpec 和实际消费者的定向测试；不把局部证据当交付 |

提交或交接时一次运行 `python3 scripts/gates/cli.py run --mode incremental`，不传 `--base` 或 selector。它覆盖 staged、unstaged、untracked 路径的**当前工作树内容**；不证明与工作树不同的部分暂存版本。
未验证的其他差异仍在范围内；输入变化需重跑，历史 receipt 不复用。Gradle 的
`UP-TO-DATE`/`FROM-CACHE` 是由原生输入和工具环境判定的复用，不是测试重跑。
Java 根 `check` 已覆盖全模块测试与零跳过时，不另跑产品 `test`；构建配置按 `AGENTS.md` 另验 `java-build`。
浏览器最终仍用原生发现完整套件；纯 Web 测试或测试模块构建不启动运行分发。Framework 对已知叶子按实际消费者发现测试，共享或未知输入仍走整套；不要把局部 spec 当全量。更多 Gate 用法见 [Gate CLI](../gates/gate-control-plane.md)。

`session-browser.sh` 只直接处理 `deps` 和 `test`；`serve` 启动前先执行 `:java:app-cli:installDist` 的 Gradle 增量构建（不运行测试），并由 Java CLI 安全替换同端口且可识别的旧 serve 进程，其他子命令原样转发给 Java CLI。详细工程规则见 [AGENTS.md](../../AGENTS.md)，脚本说明见 [scripts/README.md](../../scripts/README.md)。

修改启动链时，用 `scanCommandSmoke` 检查真实启动：它通过公开 `serve --port 0` 消费合成会话源、临时索引与终端返回的地址，不需要手工构建 launcher 或指定固定端口。

Python 项目配置和 pre-commit 配置集中在 `scripts/`；从仓库根安装或运行 hooks 时必须显式指定配置：

```bash
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv run --project scripts --frozen --extra dev pre-commit install --config scripts/.pre-commit-config.yaml
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv run --project scripts --frozen --extra dev pre-commit run --config scripts/.pre-commit-config.yaml --all-files
```

已有 pre-commit 管理的 hook 需要用新配置重新安装；不要使用强制覆盖参数替换自定义 hook。运行 hooks 可能修改代码格式，执行后检查 diff。

## 目录职责

GitHub 顶层固定为 **10 个目录 + 3 个文件**：`.agents/`、`.claude/`、`.codex/`、`.github/`、`docs/`、`harness/`、`java/`、`openspec/`、`scripts/`、`skills/`，以及 `.gitignore`、`AGENTS.md`、`README.md`。本地 ignored 缓存和运行数据不计入，不为旧入口保留转发文件或软链接。

| 目录 | 职责 |
|---|---|
| `java/` | 产品模块、Java 测试与 Java 质量规则 |
| `java/gradle/` | Wrapper、构建约定、版本目录与根依赖锁 |
| `java/gradle/config/` | Java 架构、Checkstyle、PMD 与 CPD 策略 |
| `java/tests/quality-gates/config/` | Web 质量基线 |
| `scripts/gates/config/` | Python/Java 共用术语表 |
| `docs/examples/` | 用户环境变量示例 |
| `scripts/` | 启动入口、质量检查、发布与工程脚本 |
| `scripts/tests/` | Python 工程工具与脚本测试 |
| `java/tests/` | Java 契约、浏览器测试与共享产品 fixture |
| `docs/` | 使用导航、开发说明、设计与截图资源 |
| `openspec/` | 长期规格与本地变更规划 |
| `harness/`、`skills/` | 共享 agent 策略与工作流程 |
| `.claude/`、`.codex/`、`.agents/` | 各客户端入口 |

Python 工具入口通过显式项目与配置路径发现，不在根目录保留转发配置。根项目依赖锁集中在 `java/gradle/dependency-locks/root.lockfile`；`java/settings-gradle.lockfile` 保留 Gradle 默认位置，子项目依赖锁仍由各模块管理。

## 本地产物与安全清理

- `.local/python/`：venv、工具缓存与 coverage；不是产品数据。
- `.local/gradle/`：根 Gradle 构建目录和项目缓存。
- `java/**/build/`：模块构建输出；删除后需要重新构建 launcher。
- `java/tests/playwright/node_modules/`：浏览器测试依赖。
- `tmp/`：本地任务计划、Gate/Hook/Playwright 运行记录。`FEIPI_AGENT_RUNTIME_ROOT` 未设置时，Playwright fallback 到 `tmp/agent-runtime/`。

`.gitignore` 不是删除白名单：被忽略的 `.env`、IDE 设置、SQLite 索引、工作树和 OpenSpec 变更可能有保留价值。不要直接使用 `git clean -fdX` 清空所有忽略项；先确认归属与运行状态，只删除明确可再生且未被使用的产物。

检查是否存在已跟踪的忽略项：

```bash
git ls-files -ci --exclude-standard
python3 scripts/gates/cli.py run --mode incremental --gate repositoryBoundaryAudit
```

删除本地忽略文件不会改变 GitHub 的目录列表；只有 tracked 文件的结构调整会影响主页。

源码版本的唯一真源是 `java/gradle/VERSION`；发行包内仍为根目录 `VERSION`，CLI 版本和用户命令保持不变。

工程子任务使用当前 Agent 原生 subagents；模型路由、handoff 和退役边界见 [最小 Agent 运行契约](../agent-runtime.md#原生-subagent-委派)。产品 Qoder session 支持不受工程派发退役影响。
