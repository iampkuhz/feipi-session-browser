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
| 局部 Java | 先按下文选模块静态检查和精确路径规则；通过后用 `./java/gradlew -p java :java:<module>:test --tests '*<TestClass>'` 确认原失败 |
| 页面样式/交互 | `npm --prefix java/tests/playwright test -- <相邻-spec>`；共享样式选受影响的多个 spec。结构修改可选相邻 Web 资源契约测试 |
| 工程脚本 | Shell 用 `bash -n -- <path>`，行为改动跑相邻测试。Python 先按下文检查格式和 lint，再用 `.local/python/venv/bin/python -m pytest -c scripts/pyproject.toml --rootdir . -n 0 <test-path>` 确认原失败；无运行行为时不强制测试 |
| 共享契约 | OpenSpec 和实际消费者的定向测试；不把局部证据当交付 |

### Java 静态反馈

`test --tests` 不承接格式、Checkstyle、PMD、DocLint 或 record component Javadoc；不能把单测试通过当作这些规则通过。
只选改动所属模块，不从整个脏工作区收集路径。修改 main 源码时，先运行既有原生任务（没有产品 `test`）：

```bash
./java/gradlew -p java :java:<module>:spotlessCheck :java:<module>:checkstyleMain :java:<module>:pmdMain :java:<module>:javadoc
```

仅改 test 源码时选 `:java:<module>:spotlessCheck :java:<module>:checkstyleTest`；不额外跑 main 的 PMD/Javadoc。
这些工具最小配置边界是模块/source set，不声称逐文件检查。注释语言、record component 中文 `@param`、PMD suppression 用既有聚合入口和 JavaExec 的原生 `--args`；显式传本次精确 `--paths`，不省略成全仓扫描：

```bash
env -u QUALITY_CHANGED_FILES ./java/gradlew -p java :java:tests:quality-gates:runJavaQualityGates \
  --args="--repo-root '$PWD' --paths 'java/<module>/src/main/java/<changed-file>.java' --rules java-comment-language,record-component-javadocs,no-pmd-suppressions --report-file '$PWD/java/tests/quality-gates/build/reports/java-quality-gates/summary.json'"
```

`--paths` 支持逗号分隔的多个文件或所属目录；仅改 test 时使用对应 test 路径。清除本次命令继承的 `QUALITY_CHANGED_FILES`，避免旧筛选与显式路径相交而漏查。
只设 `QUALITY_CHANGED_FILES` **不能**收窄注释语言规则，它按既有契约检查传入的所有路径；不为局部反馈修改该全量保障。删除文件不作为现存候选，无现存相关输入时不伪称规则已检查；核对摘要中的各 rule 候选数。
格式/静态规则通过后才跑原失败单点，再按消费者扩大回归；纯注释修改不强制无关行为测试。
不使用 root `check` 作为每次编辑反馈，也不把 `spotlessApply` 或自动修复挂入检查。最终交付仍按下文完整 Gate。

### Python 静态反馈

`ruff check` 不检查格式；修改 Python 后先对精确路径同时检查格式和 lint，失败先修复，不继续重测试。
保留显式配置避免根目录缓存；多文件可列出多个路径，含空格的路径需 shell 引号：

```bash
.local/python/venv/bin/ruff format --check --config scripts/pyproject.toml <path> &&
.local/python/venv/bin/ruff check --config scripts/pyproject.toml <path>
```

## 失败后的修复反馈

修复前固定原失败的最小复现；每次有边界修复后，先用同一个用例确认原症状，再根据消费者扩大到相关回归。
单点失败留在本根因诊断，相关回归失败回到对应单点；不要每修一处就执行整套检查。
最终 Gate 失败时从当前 receipt 的失败步骤和日志归组，重新进入局部闭环，不以失败本身结束任务。
选择相关回归时包含共享消费者：例如修改 Gate check 模块，除领域用例外，还检查 `scripts/tests/checks/test_shared_cli.py` 的公共入口契约，避免只覆盖新功能而遗漏已有宿主约束。
进展、停止、证据有效期和 Issue 依赖语义以共享[修复闭环](../../skills/authoring/feipi-quality-gate-diagnosis/references/repair-loop.md)为准。

### 共享 checkout 的实际写入边界

局部修复前用 `pwd`、`git rev-parse --show-toplevel`、`git status --short` 和精确路径 diff 核对任务范围、继承差异及重叠文件；只读必要片段，不展开个人配置或会话。已有差异不能据文件名归为本任务，后续只追加本任务必要 hunk。范围与来源写在现有 tasks/任务评论中即可，不要求用户逐小步登记。

最终验证前再次核对实际活动写入，而不是只看 Agent 并发数、Run 终态或 active-change 文件。可先用 `ps -axo pid,ppid,comm` 查看进程元数据，再对相关 PID 用 `lsof -a -p <PID> -d cwd -Fn` 核对 cwd；需要定位写入时仅查看该 PID 指向本 checkout 的可写 FD 元数据，不读命令行、环境或会话正文。不同聊天、编辑器、构建进程都可能写入；没有打开的写 FD 也不证明期间无人写入。

停止自己的编辑、确认已知写入来源与冲突路径后再运行最终 Gate。重叠写入未解除时保留证据、先完成不重叠部分；不覆盖他人内容，不擅停个人服务。这里没有目录排他保证，不新增 lease/锁/队列或状态文件；查询失败也不能视为已取得独占权。局部反馈仍只选本根因及实际消费者，不从 `git status` 自动收集全脏区。

### 共同环境迟滞

若 Git、模拟 Node 子进程和浏览器一起变慢，除负载、压缩及换页**增量**外，还应核对宿主到测试子进程的 macOS QoS；swap 已占用不代表正在换页，CPU 时间也不等于墙钟等待。
后台宿主可能传递 `BACKGROUND` QoS（主线程 `qos_class_self()` 为 `0x9`）。可对**本次自启的同步测试命令**用原生 `taskpolicy -a <原命令>` 作 application resource policy 对照，再回到原命令反证；固定 JDK、fixture、workers、断言及 trace，区分策略影响与缓存预热。
这不是产品修复或默认 Gate 包装器：不修改 daemon、其他 PID、机器配置，也不新增调度入口。交付若使用该条件，必须记录准确前缀与环境；局部提速仍不能替代整个工作区 Gate。

## 最终交付验证

提交或交接时一次运行 `python3 scripts/gates/cli.py run --mode incremental`，不传 `--base` 或 selector。它覆盖 staged、unstaged、untracked 路径的**当前工作树内容**；不证明与工作树不同的部分暂存版本。
未验证的其他差异仍在范围内；输入变化需重跑，历史 receipt 不复用。Gradle 的
`UP-TO-DATE`/`FROM-CACHE` 是由原生输入和工具环境判定的复用，不是测试重跑。
Java 根 `check` 已覆盖全模块测试与零跳过时，不另跑产品 `test`；构建配置按 `AGENTS.md` 另验 `java-build`。
浏览器最终仍用原生发现完整套件；纯 Web 测试或测试模块构建不启动运行分发。Framework 对已知叶子按实际消费者发现测试，共享或未知输入仍走整套；不要把局部 spec 当全量。更多 Gate 用法见 [Gate CLI](../gates/gate-control-plane.md)。

Gate 若发现验证期间输入漂移，会保留 `inputValidation` 为 FAIL 的 receipt、前后指纹和变更路径，原步骤结果仅供诊断，不是有效交付证明。确认写入来源并稳定输入后再验证，不回滚其他工作。
`changedPaths` 是前后可比较的变化；重采样读失败用 `unavailablePaths` 指向已知仓库相对路径，`afterFingerprint=null`，不伪造变化清单。Git 等无具体路径的故障保留空列表，不猜写入者。先查当前 receipt，再回到对应路径/消费者的局部诊断，避免原样重复整套。快照是前后观测，不是锁；不能保证发现中途修改后还原，ignored 构建产物也不由源码指纹证明。
浏览器 fixture 在构建后复制发行产物到本次临时目录；声明 ready 前检查页面引用的同源 JS/CSS 的状态、MIME 和内容，资源故障先于整套交互断言失败。
分发副本只隔离复制完成后的共享产物替换，不承诺并发构建/复制的原子性。多个交互失败若共用资源 HTTP 500、错误 MIME 或缺失产物，应先按该资源与服务日志归组，运行已有 readiness 合成用例/相邻消费者；没有共用证据不能合并，也不能拆成几十个产品 bug 或降低断言。

交付沿用现有任务评论或报告，清楚列出：本 Run 身份及新增 hunk/文件、继承但未由本 Run 修改的差异、局部命令与最终整个工作区 Gate 的各自范围、有效 receipt/输入指纹、未解决问题及下一责任方。最终 Gate 通过也不意味着继承差异是本 Run 所写或已获用户验收。失败/失效的 receipt 和原日志保留；附件脱敏副本附原件 SHA256、原结果/输入指纹和副本清单，不用副本哈希替代原件身份。附件补交不重跑未变输入的产品测试。

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
