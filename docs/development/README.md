# 开发与仓库结构

安装和日常使用见[首页](../../README.md)。本页只面向修改代码、运行检查的贡献者。

## 开发环境与验证

产品构建使用 JDK 25 与 Gradle Wrapper。Python 仅用于 Gate/Harness 开发工具，使用 Python 3.12 与 uv 安装锁定依赖：

验收前将 `JAVA_HOME` 设为本机实际 JDK 25 安装目录，并将 `$JAVA_HOME/bin` 放在 `PATH` 最前。交互式 shell 的 `java` 函数或别名不会自动传给 Gradle、Python 和 Node 子进程；不能只凭终端中的 `java -version` 判断构建版本。先用 `"$JAVA_HOME/bin/java" -version` 与 `./java/gradlew -p java --version` 确认 Java、Launcher JVM 和 Daemon JVM 均为 25，再运行下列检查。发行构建的 `jdeps` 和 `jlink` 跟随实际 Gradle JVM，并把 JDK 输入纳入增量判断，避免复用其他版本生成的 runtime。

```bash
# 在仓库根目录运行
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv sync --project scripts --frozen --extra dev
./scripts/session-browser.sh deps

# 修改产品代码或测试后
./scripts/session-browser.sh test

# Python 工程工具测试：仓库根与 Python 项目根分离
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv run --project scripts --frozen --extra dev python -m pytest -c scripts/pyproject.toml --rootdir . scripts/tests

# Gradle 工程根在 java/，保留 :java:* 任务名
./java/gradlew -p java check

# 提交或交接前统一增量验证
python3 scripts/gates/cli.py run --mode incremental

# 修改构建配置后额外验证
python3 scripts/gates/cli.py run --mode incremental --target java-build
```

`session-browser.sh` 只直接处理 `deps`、`test`、`quality`；其他子命令原样转发给 Java CLI。详细工程规则见 [AGENTS.md](../../AGENTS.md)，脚本说明见 [scripts/README.md](../../scripts/README.md)。

Python 项目配置和 pre-commit 配置集中在 `scripts/`；从仓库根安装或运行 hooks 时必须显式指定配置：

```bash
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv run --project scripts --frozen --extra dev pre-commit install --config scripts/.pre-commit-config.yaml
UV_PROJECT_ENVIRONMENT="$PWD/.local/python/venv" uv run --project scripts --frozen --extra dev pre-commit run --config scripts/.pre-commit-config.yaml --all-files
```

已有 pre-commit 管理的 hook 需要用新配置重新安装；不要使用强制覆盖参数替换自定义 hook。运行 hooks 可能修改代码格式，执行后检查 diff。

## 目录职责

GitHub 顶层固定为 **11 个目录 + 3 个文件**：`.agents/`、`.claude/`、`.codex/`、`.github/`、`.qoder/`、`docs/`、`harness/`、`java/`、`openspec/`、`scripts/`、`skills/`，以及 `.gitignore`、`AGENTS.md`、`README.md`。本地 ignored 缓存和运行数据不计入，不为旧入口保留转发文件或软链接。

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
| `.claude/`、`.codex/`、`.qoder/`、`.agents/` | 各客户端入口 |

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
