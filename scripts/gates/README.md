# Gate 维护手册

当前 Catalog 包含 **20 个逻辑 Gate**，并且只有一个公开入口：

```bash
# 日常提交/交接：根据当前改动自动选择 Gate
python3 scripts/gates/cli.py --mode incremental

# 人工执行一个 Gate；不看 Trigger
python3 scripts/gates/cli.py --mode incremental --gate scriptSourceStandard

# 人工执行一组 Gate；不看 Trigger
python3 scripts/gates/cli.py --mode incremental --target java-src

# 全量业务检查；选择全部 Gate
python3 scripts/gates/cli.py --mode full

# 偶尔检查环境、可执行性和 full 性能目标
python3 scripts/gates/cli.py health
```

## 一次调用到底怎么选中并执行 Gate

1. **自动增量：** `--mode incremental` 收集当前 Git 改动，用每个 Gate 的 `trigger.paths` 匹配。命中任一
   路径才选择该 Gate；未命中是 `NOT_TRIGGERED`，不是 PASS。
2. **人工单项：** `--gate NAME` 精确选择一个 Gate，忽略它的路径 Trigger，适合修复后重跑。
3. **人工分组：** `--target NAME` 选择带有该 Target 标签的全部 Gate。Target 只是方便人工批量选择，不参与
   自动规划，也不改变 Gate 的执行内容。
4. **全量：** `--mode full` 选择全部 20 个 Gate，不读取 changed paths。
5. **真正执行：** Planner 选中 Gate 后，Executor 按 `definitions.py` 中唯一 recipe 顺序执行 leaf；同一个
   Gate 不因 incremental/full、`--gate` 或 `--target` 改用另一套命令。

```text
Git 改动路径 → Gate.trigger → 选中的 Gate → 唯一 recipe → leaf owner → PASS/BLOCKED/FAIL
```

## 文件只分三层

| 位置 | 维护什么 | 不维护什么 |
|---|---|---|
| `definitions.py` | 6 个 Target、20 个 Gate、Trigger、recipe、非阻断时间目标 | 执行流程、YAML schema |
| `catalog.py` | 声明校验和按名称查询 | Gate 数据、命令执行 |
| `planner.py` / `executor.py` / `report.py` | 选择、执行、状态归约 | 第二份 Gate 清单 |
| `checks/` | 只能用 Python 表达的领域 leaf | 顶层 Gate、Target、执行计划 |
| `runtime/` | 净化环境、子进程和显式中断清理 | Gate 业务状态 |

仓库不再维护外部 YAML Catalog。修改 Gate 时只从本目录进入；`harness/` 保存跨客户端
政策真源，`scripts/harness/` 保存只读体检，它们不是另一套 Gate Catalog。

## 声明字段

| 字段 | 必须维护的内容 |
|---|---|
| `name` | 稳定 Gate ID，也是 `--gate` 的候选值 |
| `description` | 一句中文业务目的 |
| `trigger` | incremental 自动选择它的改动路径；人工 selector 和 full 不使用它 |
| `targets` | 可选的人工分组标签，不影响自动触发和执行强度 |
| `run` | 唯一 leaf recipe，以及 incremental/full 两个非阻断时间目标 |

Trigger 只有两个候选值：`changed` 表示 incremental 时由 `paths` 匹配改动；`always` 表示每次自动增量都选中。
当前 20 个 Gate 都使用 `changed`。`python-check` leaf 的 `runtime` 只有 `system`（项目运行 Python）和
`dev`（包含开发依赖的项目 Python）；其他 leaf 不维护 runtime 字段。

## 6 种 leaf 执行类型

| 类型 | Executor 实际做什么 | 实现放在哪里 |
|---|---|---|
| `command` | 按声明的 argv 直接运行 Ruff、Bandit、Vulture、Bash 或 Pytest 等标准工具 | `definitions.py` 的当前 leaf |
| `python-check` | 内部调用 Check registry，再进入唯一 `check(arguments)` | `checks/<domain>/check_*.py` |
| `gradle-task` | 运行一个 Gradle task；一个 leaf 不得隐藏多个 task | 对应 Gradle module/task |
| `java-rule` | 通过 Java QualityGateCli 运行一个 rule | `java/tests/quality-gates/` |
| `playwright` | 运行声明的 Playwright spec 集合 | `tests/playwright/` |
| `scan-smoke` | 先准备 Java distribution，再运行声明的进程级 Pytest | Java distribution + `tests/script_commands/` |

这些类型只是 Executor 的内部适配方式，不是六套公开命令。维护者仍只使用本页开头的 Gate CLI。

`增量 ≤`、`全量 ≤` 只表示健康检查期望耗时，不是 timeout。日常 Gate 会自然运行完成，不会因为超过数字
被 kill；只有显式中断才清理进程组。Markdown 不能可靠控制列宽比例，因此下表把说明集中在“如何触发和执行”
这一主列，不依赖渲染器宽度。

## 6 个 Target

| Target | 人工批量选择的范围 |
|---|---|
| `python-standard` | Python 工具链、Gate 基础设施和仓库安全 |
| `harness` | Agent、Skill、Harness 与 OpenSpec 治理 |
| `session-detail` | Web 资源和浏览器交互 |
| `java-src` | Java 源码、测试和相关规则 |
| `java-build` | Gradle 构建与 Java 工程配置 |
| `scan-script-smoke` | 扫描命令、发行 CLI 和合成样本集成 |

## 20 个逻辑 Gate

所有行都可以用 `--gate <Gate>` 人工执行；表内同时说明自动 Trigger、可用 Target 和真正 owner。

<!-- GATE-CATALOG:START -->

| Gate | 作用 | 如何触发和执行 | 增量 ≤ | 全量 ≤ |
|---|---|---|---:|---:|
| `scriptSourceStandard` | 统一检查 Python 格式、静态问题、依赖声明、安全与死代码，以及 Shell 语法。 | 自动：改动 `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` 或 `scripts/**/*.sh`。<br>人工：`--gate scriptSourceStandard`；Target `python-standard`。<br>执行：依次运行 `pythonFormat`（Ruff format）、`pythonLint`（Ruff lint/import）、`bashSyntax`（`bash -n`）、`pythonDependencyDeclarations`（deptry）、`pythonSourceSecurity`（Bandit）、`pythonDeadCode`（Vulture）；六个 leaf 全部运行。 | `≤80s` | `≤165s` |
| `pythonHarnessTests` | 运行 Harness、Gate 与质量契约的固定 Pytest 单测集合。 | 自动：改动 `pyproject.toml`、`scripts/gates/**/*.py` 或相关 Python tests。<br>人工：`--gate pythonHarnessTests`；Target `python-standard`。<br>执行：Pytest 运行 `tests/harness`、`tests/gates`、`tests/checks`、`tests/quality`、`tests/misc` 和根测试。 | `≤60s` | `≤180s` |
| `pythonDependencyVulnerabilities` | 审计 Python 锁定依赖中的已知漏洞。 | 自动：改动 `pyproject.toml` 或 `uv.lock`。<br>人工：`--gate pythonDependencyVulnerabilities`；Target `python-standard`。<br>执行：Python leaf `repository.python-dependency-vulnerabilities` 调用锁定依赖审计。 | `≤60s` | `≤120s` |
| `repositoryFilePolicy` | 统一检查仓库文件、退役路径、Git 追踪和公开脚本入口边界。 | 自动：改动 Git ignore、Agent/Harness/Skill/文档、退役产品 Python 路径或 Gate 脚本。<br>人工：`--gate repositoryFilePolicy`；Target `python-standard`。<br>执行：`repositoryFilePolicy`（`repository.repository-file-policy`）一次检查必需入口、禁止路径、全部 tracked files、退役 `src/session_browser` 和维护资料中的公开脚本引用。 | `≤15s` | `≤30s` |
| `noPythonPlaywrightSkips` | 阻止 Python 与 Playwright 测试使用会产生 skipped 结果的 API。 | 自动：改动 `tests/**/*.py`、`tests/**/*.js`、`tests/**/*.ts` 或对应 leaf。<br>人工：`--gate noPythonPlaywrightSkips`；Target `session-detail`。<br>执行：Python leaf `repository.no-python-playwright-skips` 做源码扫描。 | `≤8s` | `≤15s` |
| `currentSourcePolicy` | 检查仓库只描述当前版本和当前 Harness 状态。 | 自动：改动文档、Harness、Java、长期 OpenSpec、scripts 或相关测试。<br>人工：`--gate currentSourcePolicy`；Target `python-standard`。<br>执行：Python leaf `repository.current-source-policy`；Web 资源规则不在这里重复扫描。 | `≤10s` | `≤20s` |
| `acceptanceCaseMapping` | 检查验收用例表中的 ID 与自动化测试绑定完整一致。 | 自动：改动 `docs/acceptance-cases/**`、测试源码或对应 leaf。<br>人工：只能用 `--gate acceptanceCaseMapping`，不属于 Target。<br>执行：Python leaf `repository.acceptance-case-mapping`。 | `≤15s` | `≤30s` |
| `testDataPolicy` | 确保测试输入数据受 Git 管理、可复现，并且不依赖个人电脑或真实 Session。 | 自动：改动 `tests/**`、`java/**/src/test/**` 或对应 leaf。<br>人工：`--gate testDataPolicy`；Target `python-standard`、`java-src`。<br>执行：Python leaf `repository.test-data-policy`；fixture 的 `README.md` 只作维护说明，不当作测试输入。 | `≤15s` | `≤30s` |
| `secretLikeContent` | 扫描仓库中的密钥、Token 与凭据形态内容。 | 自动：改动测试、文档、Java、Agent/Harness、Skill 或 scripts。<br>人工：`--gate secretLikeContent`；Target `python-standard`。<br>执行：Python leaf `security.secret-like-content`。 | `≤20s` | `≤45s` |
| `languagePolicy` | 统一检查仓库政策文本与脚本注释符合中文维护规范。 | 自动：改动 Agent/Skill/Harness/OpenSpec、脚本或术语表。<br>人工：`--gate languagePolicy`；Target `harness`、`python-standard`、`java-build`。<br>执行：`languagePolicy`（`repository.language-policy`）与 `scriptCommentLanguage`（`source.comment-language`）两个 Python leaf，全部运行。 | `≤18s` | `≤35s` |
| `agentPolicy` | 统一检查 Agent 运行配置与维护文档政策。 | 自动：改动 Agent 配置、Skill、Harness 或 `scripts/gates/**`。<br>人工：`--gate agentPolicy`；Target `harness`。<br>执行：`agentRuntimePolicy`（`agent.runtime-policy`，入口与权限）和 `agentDocumentPolicy`（`agent.document-policy`，体积、受保护路径与 handoff）两个 Python leaf，分别只读取一次共享输入。 | `≤30s` | `≤60s` |
| `governanceStructure` | 统一验证 Skill registry、Harness 结构与 OpenSpec 布局。 | 自动：改动 Skill registry、Skill、Harness、OpenSpec 或对应 validator。<br>人工：`--gate governanceStructure`；Target `harness`。<br>执行：`skillRegistry`（`agent.skill-registry`）、`harnessStructure`（`scripts/harness/validate_harness_structure.py`）、`openspecLayout`（`scripts/openspec/validate_layout.py`）。 | `≤24s` | `≤45s` |
| `webSourcePolicy` | 统一检查 Web 模板、脚本、静态资源与 CSS 源码政策。 | 自动：改动 Web resources、Java quality rules、Web baseline 或相关 JS/Gate tests。<br>人工：`--gate webSourcePolicy`；Target `session-detail`、`python-standard`、`java-src`。<br>执行：`rawInnerhtml`（`raw-innerhtml`）、`layoutInlineStyle`（`layout-inline-style`）、`templateContract`（`template-contract`）、`staticCssContract`（`static-resource-contract`）、`cssOwnership`（`css-ownership`）五个 Java rule；其中 `staticCssContract` 唯一负责 viewport、空 JS、无效 CSS 和旧隐藏兼容选择器。 | `≤90s` | `≤180s` |
| `webResourceTests` | 运行 Java Web 模板、CSS 与 JavaScript 的资源契约测试。 | 自动：改动 Web templates/static；Java test 自身改动由 `javaCheck` 处理。<br>人工：`--gate webResourceTests`；Target `session-detail`、`java-src`。<br>执行：Gradle task `:java:web:test`。 | `≤60s` | `≤180s` |
| `browserLayout` | 用 Playwright 验证主要页面、布局与视觉壳层契约。 | 自动：改动 Web templates/static 或 `tests/playwright/**`。<br>人工：`--gate browserLayout`；Target `session-detail`。<br>执行：Playwright `ui-contract.spec.ts`、`main-pages-visual.spec.ts`、`session-detail-layout`、`shell-states`、`dashboard-chart-coordinates`。 | `≤90s` | `≤240s` |
| `browserInteraction` | 用 Playwright 验证 Session、列表与迁移页面交互。 | 自动：改动 Web templates/static 或 `tests/playwright/**`。<br>人工：`--gate browserInteraction`；Target `session-detail`。<br>执行：Playwright `session-detail.spec.js`、`session-detail-migrated-gates.spec.js`、`sessions-list.spec.js`。 | `≤90s` | `≤240s` |
| `javaCheck` | 运行 Java 编译、测试和标准源码规则。 | 自动：改动 Java/Kotlin 源码或测试、Gradle 与模块构建配置、技术词表或锁文件。<br>人工：`--gate javaCheck`；Target `java-src`、`java-build`。<br>执行：Gradle root `check`；原生任务图统一负责编译、测试、零 skipped/aborted、中文注释、record Javadoc、PMD suppression 与 PMD，不再由其他 Gate 重复执行。 | `≤240s` | `≤600s` |
| `javaReusePolicy` | 使用 CPD 检查 Java 生产源码中的重复实现。 | 自动：改动 Java 生产源码、reuse policy 或 Gradle 配置。<br>人工：`--gate javaReusePolicy`；Target `java-src`、`java-build`。<br>执行：只运行独立 Gradle task `reuseStandardCpd`；PMD 已由 `javaCheck` 负责。 | `≤180s` | `≤600s` |
| `scanScriptSmoke` | 验证 session-browser scan 命令与发行 CLI 的进程级契约。 | 自动：改动 `scripts/session-browser.sh`、扫描/来源/索引/CLI 模块、Gate checks 或 smoke tests。<br>人工：`--gate scanScriptSmoke`；Target `scan-script-smoke`。<br>执行：先运行 `:java:app-cli:installDist`，再运行 `tests/script_commands/test_session_browser_scan_smoke.py`。 | `≤90s` | `≤180s` |
| `sessionSamples` | 用合成 Session 样本验证解析、标准化与契约集成。 | 自动：改动 `tests/fixtures/session_samples/**`、标准化模型、sources/engine/artifact 或相邻 contract test。<br>人工：`--gate sessionSamples`；Target `scan-script-smoke`。<br>执行：Gradle task `:java:tests:contracts:sampleIntegrationTest`。 | `≤90s` | `≤240s` |

<!-- GATE-CATALOG:END -->

## 状态与 composite

| 状态 | 含义 | 下一步 |
|---|---|---|
| `PASS` | Gate/leaf 完整执行且没有问题 | 继续 |
| `BLOCKED` | 检查完整执行并确认源码、规则或 warning 阻断 | 修复仓库内容后重跑 |
| `FAIL` | Gate 没有完成或无法判断，包括 skip/not-run/unavailable | 修复执行环境、输入或 owner 后重跑 |

Owner 退出码是 `0=PASS`、`1=BLOCKED`、`2=FAIL`。Composite 不 fail-fast：任一 FAIL 则 Gate FAIL；否则任一
BLOCKED 则 Gate BLOCKED；只有全部 leaf PASS 才 PASS。

`bash scripts/harness/doctor.sh` 是可单独运行的只读诊断，不是第 21 个 Gate。综合环境检查使用
`python3 scripts/gates/cli.py health`，但 health 不是日常交接证据。

## 修改步骤

1. 在 `definitions.py` 找到唯一 Gate declaration，修改 Trigger、Target、recipe 或时间目标。
2. Python leaf 只在 `checks/<domain>/check_*.py` 实现，并在 `checks/_registry.py` 登记；Java/Gradle/Playwright
   继续由原生 owner 实现。
3. 更新本表“如何触发和执行”，明确自动路径、人工 `--gate`、Target 和真实 owner。
4. 运行 catalog/planner/documentation contract 和相关 owner test，再用 `--dry-run` 查看计划。
5. 最后运行 `python3 scripts/gates/cli.py --mode incremental`。旧 ID、旧路径和 wrapper 不保留。
