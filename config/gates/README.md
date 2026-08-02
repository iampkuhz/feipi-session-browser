# Gate 使用手册

## 一页结论

- 仓库当前只有**一份最新版 Catalog**，不记录 Catalog 版本，也不保留旧版字段或兼容入口。
- 当前共有 **42 个逻辑 Gate**；其中 **40 个可进入 `required`**，另外 2 个只在 `full` 中运行。
- 当前共有 **8 个 target**。Target 是“验证场景”，Gate 是场景中的“具体检查”。
- 唯一配置入口是 [`../gates.yaml`](../gates.yaml)，具体 Gate 按领域拆在本目录的 6 个 YAML 中。
- 每次执行都先运行一个统一的 `repositoryFilePolicy`，不再让三个名称相近的仓库文件检查分别出现。

`pythonDependencyVulnerabilities` 和 `javaApiSnapshot` 是仅限 `full` 的两个 Gate。前者需要联网查询依赖
漏洞，网络不可用时结果是 `BLOCKED`；后者检查 Java 公开 API 快照。“可进入某个 tier”不表示本次已触发，
更不表示已经通过。

## 先理解四个术语

| 术语 | 人能理解的含义 | 配置或代码位置 |
|---|---|---|
| **changed file** | 当前真正改动的仓库相对路径 | `scripts/gates/cli.py::get_changed_files` |
| **target** | 一类改动对应的验证套餐，例如 Java 源码或 Session Detail | `config/gates.yaml` 的 `targets` |
| **Gate** | 套餐中的一项具体检查，例如 `javaCheck` 或 `pythonLint` | `config/gates/*.yaml` |
| **tier** | 执行强度：`quick`、`required`、`full` | CLI 的 `--tier` 与 Gate 的 `minimum_tier` |

一个文件可以触发多个 target；一个 Gate 也可以参加多个 target。最终执行前按 Gate 名去重，所以同一个 Gate
最多运行一次。Target 不是脚本、Gradle task 或 owner，它只回答“这次改动要检查哪些领域”。

## 8 个 Target 的完整目录

| Target | 它代表的改动场景 | 常见输入 | 候选 Gate 数 |
|---|---|---|---:|
| `python-standard` | Python、脚本和通用仓库治理 | `scripts/**/*.py`、`tests/**/*.py`、`pyproject.toml` | 16 |
| `harness` | Agent、Harness、Skill 与 OpenSpec 治理 | `harness/**`、`skills/**`、Agent 配置 | 7 |
| `acceptance-cases` | 验收用例表与自动化测试绑定 | `docs/acceptance-cases/**`、各语言测试 | 5 |
| `session-detail` | Web 模板、静态资源与浏览器交互 | `java/web/src/main/resources/**`、`tests/playwright/**` | 9 |
| `index` | Session 索引结构与完整性 | 显式 `--target index` 或 `full` | 1 |
| `java-src` | Java/Kotlin 生产源码和测试源码 | `java/**/src/main/**`、`java/**/src/test/**` | 15 |
| `java-build` | Gradle 与 Java 构建配置 | `gradle/**`、`*.gradle.kts`、Java 质量配置 | 6 |
| `scan-script-smoke` | scan CLI、扫描引擎、数据源和合成样本 | scan 相关脚本、Java 模块和 fixture | 2 |

候选数不能相加，因为同一个 Gate 可以属于多个 target。`java-src` 的 `includes: [java-build]` 只是去重规则：
一次改动同时得到这两个 target 时只保留 `java-src` 场景，不是文件包含关系。

## 从一个改动文件到真正执行的 Gate

按自然语言理解，完整流程是：

1. **收集改动文件。** `scripts/gates/cli.py` 读取显式 `--changed-files`；没有显式输入时，再读取当前任务证据和
   Git 改动。
2. **由文件选择 target。** `scripts/gates/planner.py` 用改动路径匹配 `config/gates.yaml` 中
   `path_rules[].patterns`，命中后取该规则的 `targets`。`target_triggers` 只负责补充特殊场景，例如 scan 冒烟。
3. **整理 target。** 去重后应用 `targets[].includes`，得到本次真正需要检查的验证场景。
4. **由 target 选择 Gate。** Planner 再进入 `config/gates/*.yaml`，找到声明了该 target 的 Gate，并用 Gate
   自己的 `targets[].patterns` 再匹配一次。`patterns` 决定是否选中，`order` 只决定同一 target 内的顺序；
   空 `patterns` 表示 target 一旦出现就运行。
5. **应用 tier。** `required` 接受最低档位为 `quick` 或 `required` 的 Gate，不接受仅限 `full` 的 Gate。
6. **生成命令并执行。** CLI 先加入统一仓库文件预检 `repositoryFilePolicy`，再由
   `scripts/gates/executor.py` 把每个 Gate 的 `run` 变成真实命令并执行。

例如修改 `docs/acceptance-cases/features/HOOK_HARNESS.md`：第一层规则把它分到 `acceptance-cases`；第二层规则
选中 `acceptanceCaseMapping`；tier 过滤后，加上固定的 `repositoryFilePolicy`，才形成最终计划。

因此两层 `patterns` 的职责不同：**根 YAML 的 pattern 做“文件 → target”，分片 YAML 的 pattern 做
“target + 文件 → Gate”。**

## YAML 现在需要维护哪些字段

### 根索引 `config/gates.yaml`

| 字段 | 是否必需 | 作用 |
|---|---|---|
| `gate_defaults` | 是 | 统一保存公共 `tier`、超时、changed-files 输入和网络失败策略 |
| `targets` | 是 | 声明 8 个验证场景，以及少量 `includes` 去重关系 |
| `gate_files` | 是 | 声明 6 个 Gate 分片及读取顺序 |
| `path_rules` | 是 | 第一层“改动文件 → target”规则 |
| `target_triggers` | 是 | 补充无法用单一分类表达的特殊 target 触发条件 |

根索引没有 `version`。增加 `version` 会被严格解析器直接拒绝，避免人工维护无意义的历史编号。

### 每个 Gate

每个 Gate 只需四类核心信息：`name`、中文 `description`、`targets` 和唯一一个 `run`。每条 target 规则包含：

- `name`：所属 target；
- `order`：该 target 中的执行顺序；
- `patterns`：哪些改动会选中它，空列表表示 target 命中即运行。

`minimum_tier`、`timeout`、`changed_files`、`network_failure` 只有偏离 `gate_defaults` 时才写，禁止重复填写默认值。

## “执行方式”列怎么读

原来的“实现入口”和“执行通道”信息重复，现合并为一列 **执行方式**。候选值固定为 6 类：

| 执行方式 | 含义 | 最终执行通道 |
|---|---|---|
| `Command · ...` | 直接运行固定工具或测试命令 | 有界子进程 |
| `Python Check · <check-id>` | 通过 `python3 -m scripts.checks <check-id>` 调用唯一 Python Check | 有界子进程 |
| `Playwright · configured suite` | 运行 Catalog 中固定的浏览器用例集合 | 有界子进程 |
| `Scan Smoke · configured suite` | 构建必要 Java 程序后运行固定 scan 进程冒烟 | 有界子进程 |
| `Gradle Task · <task>` | 运行已有 Gradle task | 聚合 Gradle 进程 |
| `Java Rule · <rule-id>` | 交给 Java quality-gates 模块执行规则 | 聚合 Gradle 进程 |

完整表格中其余属性含义：

- **Gate**：稳定的逻辑检查名；
- **作用**：它保护的业务或工程结果；
- **Target**：它参加哪些验证场景；
- **Tier**：允许它进入计划的最低执行强度；
- **主要触发点**：最多列 3 个真实 pattern；“Target 命中即运行”表示 pattern 为空。

## 几个容易混淆的 Gate

### 仓库文件政策

`repositoryFilePolicy` 已合并原来分散的仓库结构、Git ignore 和禁止路径检查，只做四件事：

1. 必需的维护入口必须存在；
2. `harness/manifest.yaml` 的 `forbidden_root_paths` 中列出的目录或文件不得出现在仓库根目录；
3. 被 `.gitignore` 命中的文件不得同时进入 Git tracked；
4. 禁止根路径和数据库文件不得进入 Git tracked。

这里的 `harness/manifest.yaml` 可以理解为“仓库维护清单”：它集中列出公开命令、质量场景和禁止放在仓库根目录
的运行产物。`forbidden_root_paths` 不是“所有生成文件”，而是一份明确的根目录黑名单，例如 `.venv/`、
`output/` 和 `.pytest_cache/`。

### 当前源码政策

`currentSourcePolicy` 是原先名称含糊的瘦身检查，固定只有四条规则：

1. 当前源码和维护文档不记录历史版本标记；
2. Harness 只描述当前可执行状态，不保存删除或迁移日志；
3. Web 只声明当前支持的桌面视口；
4. CSS/JavaScript 不保留空文件或无效兼容垫片。

### 测试不得跳过

| Gate | 负责范围 |
|---|---|
| `noPythonPlaywrightSkips` | Python 的 `skip`/`skipif`/`importorskip` 和 Playwright 的 `skip`/`fixme` |
| `noJavaTestSkips` | Gradle/JUnit 产生的 skipped 或 aborted 结果 |

两者按语言工具链分开，不重复扫描。

### 测试数据政策

`testDataPolicy` 的目标不是只找某一种真实 Session fixture，而是保证测试可复现：

- `tests/**/fixtures/**` 和 `java/**/src/test/resources/**` 中的数据文件必须被当前仓库 Git 跟踪；
- 测试不得从仓库外绝对路径读取固定数据，因此不能依赖某台电脑的目录结构；
- 允许测试框架提供的动态临时目录，例如 Pytest `tmp_path` 和 JUnit `@TempDir`；
- 测试源码和数据不得包含真实 Session、个人用户名或个人设备路径；诊断不回显敏感内容。

## 测试执行归属

| Gate | 唯一执行范围 |
|---|---|
| `pythonHarnessTests` | Harness、Gate、Check、quality、misc 和根目录 Python 单测 |
| `scanScriptSmoke` | `tests/script_commands/test_session_browser_scan_smoke.py` 进程冒烟 |
| `webResourceTests` | `:java:web:test` 中的模板、CSS、JavaScript 资源契约 JUnit 测试 |

`acceptanceCaseMapping` 只检查“验收用例 ID ↔ 自动化测试”的映射，不执行测试。Playwright 由
`browserLayout` 和 `browserInteraction` 执行。不要再为已有 Java/Gradle 测试增加一层 Python 包装。

<!-- GATE-CATALOG:START -->

## Python 与脚本工具（9）

完整声明：[`python-tooling.yaml`](python-tooling.yaml)

<!-- gate-file: gates/python-tooling.yaml -->
| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|
| `pythonFormat` | 校验仓库 Python 源码符合 Ruff 格式化结果。 | `Command · ruff format` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonLint` | 检查 Python 静态问题与 import 顺序。 | `Command · ruff check` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonHarnessTests` | 运行 Harness、Gate 与质量契约的固定 Pytest 单测集合。 | `Command · pytest (harness tests)` | `python-standard` | `required` | `pyproject.toml`、`config/gates.yaml`、`config/gates/**` |
| `pythonSourceSecurity` | 使用 Bandit 对 scripts Python 源码执行离线安全扫描。 | `Command · bandit` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py` |
| `pythonDependencyVulnerabilities` | 审计 Python 锁定依赖中的已知漏洞。 | `Python Check · repository.python-dependency-vulnerabilities` | `python-standard` | `full` | `pyproject.toml`、`uv.lock` |
| `pythonDeadCode` | 检查 scripts 与测试中的高置信度无引用 Python 代码。 | `Command · vulture` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonDependencyDeclarations` | 检查 scripts 的 Python 依赖声明完整性。 | `Command · deptry` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py` |
| `bashSyntax` | 使用 bash 语法解析器检查仓库 Shell 脚本。 | `Command · bash -n` | `python-standard` | `quick` | `scripts/**/*.sh` |
| `scriptCommentLanguage` | 检查 Python、Shell 注释语言与技术术语符合中文维护规范。 | `Python Check · source.comment-language` | `python-standard、java-build` | `required` | `scripts/**/*.py`、`scripts/**/*.sh`、`config/technical-terms.json` |

## 仓库、测试、隐私与安全（6）

完整声明：[`repository-safety.yaml`](repository-safety.yaml)

<!-- gate-file: gates/repository-safety.yaml -->
| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|
| `repositoryFilePolicy` | 统一检查必需入口、禁止根路径、Git 忽略规则和数据库文件边界。 | `Python Check · repository.repository-file-policy` | `python-standard` | `quick` | `.gitignore`、`harness/manifest.yaml`、`scripts/checks/repository/check_repository_file_policy.py` |
| `noPythonPlaywrightSkips` | 阻止 Python 与 Playwright 测试使用会产生 skipped 结果的 API。 | `Python Check · repository.no-python-playwright-skips` | `acceptance-cases、session-detail` | `quick` | `tests/**/*.py`、`tests/**/*.js`、`tests/**/*.ts` |
| `currentSourcePolicy` | 检查源码只描述当前版本、当前 Harness、桌面视口和有效静态资源。 | `Python Check · repository.current-source-policy` | `python-standard` | `required` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`harness/**` |
| `acceptanceCaseMapping` | 检查验收用例表中的 ID 与自动化测试绑定完整一致。 | `Python Check · repository.acceptance-case-mapping` | `acceptance-cases` | `required` | `docs/acceptance-cases/**/*.md`、`tests/**/*.py`、`tests/**/*.js` |
| `testDataPolicy` | 确保测试数据受 Git 管理、可复现，并且不依赖个人电脑或真实 Session。 | `Python Check · repository.test-data-policy` | `acceptance-cases、python-standard、java-src` | `required` | `tests/**`、`java/**/src/test/**`、`scripts/checks/repository/check_test_data_policy.py` |
| `secretLikeContent` | 扫描仓库中的密钥、Token 与凭据形态内容。 | `Python Check · security.secret-like-content` | `python-standard` | `required` | `tests/**`、`docs/**`、`java/**` |

## Agent、Harness 与 OpenSpec（8）

完整声明：[`harness-governance.yaml`](harness-governance.yaml)

<!-- gate-file: gates/harness-governance.yaml -->
| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|
| `languagePolicy` | 检查仓库规则、Skill 与 Harness 文本符合中文语言政策。 | `Python Check · repository.language-policy` | `harness` | `quick` | `AGENTS.md`、`CLAUDE.md`、`skills/**` |
| `protectedRootsSync` | 检查各 Agent 入口声明的受保护路径与共享政策一致。 | `Python Check · agent.protected-roots` | `harness` | `quick` | `AGENTS.md`、`CLAUDE.md`、`.agents/**` |
| `subagentHandoffProtocol` | 检查 subagent handoff 字段、状态和失败策略在各入口保持一致。 | `Python Check · agent.subagent-handoff` | `harness` | `quick` | `AGENTS.md`、`CLAUDE.md`、`.agents/**` |
| `doctor` | 只读检查 Harness 依赖、结构与配置是否可用。 | `Command · scripts/harness/doctor.sh` | `python-standard` | `quick` | `scripts/harness/**/*.sh` |
| `agentPolicySize` | 限制 Agent 入口与共享政策体积，防止规则重新膨胀。 | `Python Check · agent.policy-size` | `harness` | `required` | `AGENTS.md`、`CLAUDE.md`、`.codex/config.toml` |
| `skillRegistry` | 检查共享 Skill registry、平台入口与物理目录一致。 | `Python Check · agent.skill-registry` | `harness` | `required` | `harness/skill-registry.yaml`、`skills/**`、`.agents/skills/**` |
| `harnessStructure` | 验证 Harness manifest、Skill 链接和目录结构契约。 | `Command · scripts/harness/validate_harness_structure.py` | `harness` | `quick` | `harness/**`、`scripts/harness/**/*.py` |
| `openspecLayout` | 验证 OpenSpec 目录布局和必需文件。 | `Command · scripts/openspec/validate_layout.py` | `harness` | `required` | `openspec/**` |

## Web UI 与浏览器检查（8）

完整声明：[`web-quality.yaml`](web-quality.yaml)

<!-- gate-file: gates/web-quality.yaml -->
| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|
| `rawInnerhtml` | 阻止 JavaScript 使用未受控的 innerHTML 原始写入。 | `Java Rule · raw-innerhtml` | `session-detail、acceptance-cases、python-standard、java-src` | `required` | `java/web/src/main/resources/static/js/**/*.js`、`config/web-quality-baselines.json`、`tests/**/*.js` |
| `layoutInlineStyle` | 阻止模板或 JavaScript 绕过样式层直接写布局属性。 | `Java Rule · layout-inline-style` | `session-detail、java-src` | `required` | `java/web/src/main/resources/static/js/**/*.js`、`java/web/src/main/resources/templates/**/*.html`、`config/web-quality-baselines.json` |
| `templateContract` | 检查 Web 模板不使用遗留标记或不安全的内联交互。 | `Java Rule · template-contract` | `session-detail、java-src` | `required` | `java/web/src/main/resources/templates/**`、`java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRule.java`、`java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRuleTest.java` |
| `staticCssContract` | 检查 Web 静态资源加载、CSS 结构与基线契约。 | `Java Rule · static-resource-contract` | `session-detail、java-src` | `required` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`java/web/src/main/resources/templates/**/*.html` |
| `cssOwnership` | 检查顶层 CSS 的组件归属、设计变量与选择器边界。 | `Java Rule · css-ownership` | `session-detail、python-standard、acceptance-cases、java-src` | `required` | `java/web/src/main/resources/static/css/**/*.css`、`scripts/gates/executor.py`、`tests/gates/test_executor.py` |
| `webResourceTests` | 运行 Java Web 模板、CSS 与 JavaScript 的资源契约测试。 | `Gradle Task · :java:web:test` | `session-detail、java-src` | `required` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`java/web/src/test/java/com/feipi/session/browser/web/page/**` |
| `browserLayout` | 用 Playwright 验证主要页面、布局与视觉壳层契约。 | `Playwright · configured suite` | `session-detail` | `required` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` |
| `browserInteraction` | 用 Playwright 验证 Session、列表与迁移页面交互。 | `Playwright · configured suite` | `session-detail` | `required` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` |

## Java 构建与源码质量（8）

完整声明：[`java-quality.yaml`](java-quality.yaml)

<!-- gate-file: gates/java-quality.yaml -->
| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|
| `javaCheck` | 运行 Java 模块编译、单元测试与标准 Gradle 检查。 | `Gradle Task · check` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`**/*.java` |
| `javaChineseComments` | 检查 Java、Kotlin 与 Gradle 注释符合中文和术语政策。 | `Java Rule · java-comment-language` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`java/**/src/main/kotlin/**/*.kt` |
| `javaRecordComponentJavadocs` | 检查公开 record component 具有匹配的 Javadoc 参数说明。 | `Java Rule · record-component-javadocs` | `java-src` | `required` | `java/**/src/main/java/**/*.java`、`**/*.java` |
| `noJavaTestSkips` | 阻止 Java 测试出现 skipped 或 aborted 结果。 | `Gradle Task · verifyNoSkippedJavaTests` | `java-src` | `quick` | `java/**/src/test/java/**/*.java` |
| `noJavaSuppressWarnings` | 阻止 Java 生产源码新增 PMD 抑制注解。 | `Java Rule · no-pmd-suppressions` | `java-src` | `quick` | `java/**/src/main/java/**/*.java` |
| `reuseStandardCpd` | 按共享复用政策执行 Java CPD 重复代码检查。 | `Gradle Task · reuseStandardCpd` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` |
| `reuseAnalyzeIncremental` | 生成 Java 增量复用分析证据并检查政策变更。 | `Gradle Task · reuseAnalyzeIncremental` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` |
| `javaApiSnapshot` | 比较公开 Java API 与受控快照，防止未审阅的兼容变化。 | `Java Rule · java-api-snapshot` | `java-src、java-build` | `full` | `config/api-snapshots/java-public-api.txt`、`java/**/src/main/java/**/*.java` |

## 索引与产品冒烟（3）

完整声明：[`product-smoke.yaml`](product-smoke.yaml)

<!-- gate-file: gates/product-smoke.yaml -->
| Gate | 作用 | 执行方式 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|
| `indexIntegrity` | 检查本地 Session 索引文件、表结构与关键字段完整性。 | `Python Check · repository.index-integrity` | `index` | `required` | `scripts/checks/repository/check_index_integrity.py` |
| `scanScriptSmoke` | 验证 session-browser scan 命令与发行 CLI 的进程级契约。 | `Scan Smoke · configured suite` | `scan-script-smoke` | `required` | `scripts/session-browser.sh`、`java/app-cli/**`、`java/scan-engine/**` |
| `sessionSamples` | 用合成 Session 样本验证解析、标准化与契约集成。 | `Gradle Task · :java:tests:contracts:sampleIntegrationTest` | `scan-script-smoke` | `required` | `tests/fixtures/session_samples/**`、`java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**`、`java/sources/**` |

<!-- GATE-CATALOG:END -->

## 修改规则

1. 先在对应领域 YAML 修改 Gate；不要在多个文件复制同名 Gate。
2. 从 6 种 `run` 中选择一种；不要再增加“包装已有测试命令”的 Python 文件。
3. 同步更新本页，并运行 catalog 与文档契约测试。
4. 删除或改名时确认旧 Gate 名、旧 Check ID、旧路径和旧术语零引用；不保留 alias 或历史版本记录。
5. 最后运行受影响的 target 和 `python3 scripts/gates/cli.py --tier required`。
