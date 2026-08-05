# Gate 使用手册

## 一页结论

- 仓库只有一份最新版 Catalog，不维护版本号或旧字段兼容。
- 当前共有 **41 个逻辑 Gate**，每个 Gate 都有独立的 incremental/full profile。
- 当前共有 **6 个 Target preset**；Target 只供人工选择，不参与自动规划。
- `docs/acceptance-cases/` 是验收用例总账，不是 Target。
- Gate 顶层固定为 `name/description/trigger/targets/run` 五个字段。

普通提交和交接运行：

```bash
python3 scripts/gates/cli.py --mode incremental
```

发布、周期审计或大迁移运行：

```bash
python3 scripts/gates/cli.py --mode full
```

## 先理解五个术语

| 术语 | 自然语言含义 | 配置位置 |
|---|---|---|
| changed file | 当前 checkout 真正改动的仓库相对路径 | CLI 收集或显式 `--changed-files` |
| Trigger | Gate 自己声明哪些改动会自动选择它 | Gate 的 `trigger` |
| Gate | 一项有明确结论的具体检查 | `config/gates/*.yaml` |
| Target | 人工一次选择一组 Gate 的 preset/tag | `config/gates.yaml` 的 `targets` |
| mode | 只表示执行范围，候选仅 `incremental/full` | CLI 的 `--mode` 与 Gate 的双 profile |

`incremental` 不等于“快速”，`full` 也不等于“required”。每个 Gate 自己维护两种 mode 的执行内容和时效，
外部只选择范围，不按耗时决定是否运行。

## 自动增量选择链路

用自然语言理解：

1. CLI 收集当前改动文件，并统一成仓库相对路径。
2. Planner 逐个读取每个 Gate 的 `trigger`；路径命中时直接选择该 Gate。
3. Executor 读取被选 Gate 的 `run.incremental` profile 并执行。
4. Report 归约为 PASS、BLOCKED 或 FAIL，并记录实际耗时与 Gate 自己的目标耗时。

```text
changed files → Gate.trigger → selected Gates → incremental profile → result
```

Target 不在这条自动链路里。只有维护者显式传入 `--target NAME` 时，它才作为人工 preset 选择成员并绕过
Trigger。`--mode full` 选择全部 41 个 Gate，同样绕过 Trigger。

根 `path_rules` 只为改动文件附加风险分类和审计信息，不选择 Target，也不选择 Gate。

## Target preset 目录

| Target | 用途 | Gate 数 |
|---|---|---:|
| `python-standard` | 人工运行 Python 工具链与质量基础设施相关 Gate。 | 16 |
| `harness` | 人工运行 Agent、Skill、Harness 与 OpenSpec 治理 Gate。 | 7 |
| `session-detail` | 人工运行 Web 页面、静态资源与浏览器交互 Gate。 | 9 |
| `java-src` | 人工运行 Java 源码与测试质量 Gate。 | 15 |
| `java-build` | 人工运行 Gradle 构建与 Java 工程配置 Gate。 | 6 |
| `scan-script-smoke` | 人工运行扫描命令、发行 CLI 与样本集成 Gate。 | 2 |

Target 数不能相加，因为同一个 Gate 可以加入多个人工 preset。Target 没有 pattern、执行档位、order、includes 或
dominance。选择不到 Gate 的空 Target 会返回 FAIL。

## YAML 字段

### 根索引 `config/gates.yaml`

| 字段 | 作用 |
|---|---|
| `targets` | 注册 6 个只供人工选择的 preset，以及中文说明 |
| `gate_files` | 声明 6 个领域 Gate 分片及稳定读取顺序 |
| `path_rules` | 只做文件风险分类，不参与 Gate 选择 |

### Gate 顶层五字段

| 字段 | 是否必填 | 作用 |
|---|---:|---|
| `name` | 是 | 唯一 Gate ID、报告名和 `--gate` 候选值 |
| `description` | 是 | 用中文单句说明检查目的 |
| `trigger` | 是 | 自动 incremental 选择；`mode` 仅 `always/changed` |
| `targets` | 否 | 所属人工 preset；默认空列表 |
| `run` | 是 | 一种 typed adapter 及完整 incremental/full profile |

`trigger.mode: changed` 必须提供非空 `paths`；`always` 禁止提供 paths。full、`--target` 和 `--gate` 都绕过
Trigger。

每个 `run.incremental` 和 `run.full` 都维护执行内容、`target_seconds` 与 `timeout_seconds`。
`target_seconds` 是 Gate 自己的优化目标，不参与 Planner 选择；`timeout_seconds` 是异常终止上限且不得小于目标。
full 执行内容相同时可以写 `same_as: incremental`，但两个时效仍需明确维护。

六种执行方式固定为：`Command · ...`、`Python Check · <check-id>`、`Playwright · configured suite`、
`Scan Smoke · configured suite`、`Gradle Task · <task>`、`Java Rule · <rule-id>`。

完整表中的“增量/全量目标”统一写作“目标耗时 / timeout”，不是外部执行强度。

## 状态语义

| 状态 | 是否完整执行 | 是否已判断仓库 | 下一步 |
|---|---:|---:|---|
| `PASS` | 是 | 是，没有问题 | 继续 |
| `BLOCKED` | 是 | 是，确认存在阻断问题 | 先修改仓库，再重跑 |
| `FAIL` | 否 | 否，无法判断 | 先恢复工具、环境、输入或依赖，再重跑 |

owner 退出码固定为 `0=PASS`、`1=BLOCKED`、`2=FAIL`。漏洞、lint 命中和测试断言失败属于 BLOCKED；
runtime 缺失、网络不可用、timeout、skip/no-source 属于 FAIL。`NOT_TRIGGERED` 只表示自动增量规划没有选中，
不是 Gate 终态。对外 overall 只有 `PASS/NOT_PASS`。

## 测试执行与验收用例归属

`acceptanceCaseMapping` 只检查验收用例 ID、结构化绑定和代码位置，不执行测试。Python、JUnit 与 Playwright
测试仍由各自 Gate 执行。测试源码变更既触发对应执行 Gate，也通过 mapping Gate 自己的 Trigger 触发映射检查。
不要为已有 Java/Gradle 测试新增 Python 包装。

<!-- GATE-CATALOG:START -->

## Python 与脚本工具（9）

完整声明：[`python-tooling.yaml`](python-tooling.yaml)

<!-- gate-file: gates/python-tooling.yaml -->
| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |
|---|---|---|---|---|---|---|
| `pythonFormat` | 校验仓库 Python 源码符合 Ruff 格式化结果。 | `Command · ruff format` | `python-standard` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` | `10s / 60s` | `20s / 120s` |
| `pythonLint` | 检查 Python 静态问题与 import 顺序。 | `Command · ruff check` | `python-standard` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` | `15s / 60s` | `30s / 120s` |
| `pythonHarnessTests` | 运行 Harness、Gate 与质量契约的固定 Pytest 单测集合。 | `Command · pytest (harness tests)` | `python-standard` | `pyproject.toml`、`config/gates.yaml`、`config/gates/**` | `60s / 240s` | `180s / 600s` |
| `pythonSourceSecurity` | 使用 Bandit 对 scripts Python 源码执行离线安全扫描。 | `Command · bandit` | `python-standard` | `pyproject.toml`、`scripts/**/*.py` | `20s / 90s` | `45s / 180s` |
| `pythonDependencyVulnerabilities` | 审计 Python 锁定依赖中的已知漏洞。 | `Python Check · repository.python-dependency-vulnerabilities` | `python-standard` | `pyproject.toml`、`uv.lock` | `60s / 180s` | `120s / 360s` |
| `pythonDeadCode` | 检查 scripts 与测试中的高置信度无引用 Python 代码。 | `Command · vulture` | `python-standard` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` | `15s / 60s` | `30s / 120s` |
| `pythonDependencyDeclarations` | 检查 scripts 的 Python 依赖声明完整性。 | `Command · deptry` | `python-standard` | `pyproject.toml`、`scripts/**/*.py` | `15s / 60s` | `30s / 120s` |
| `bashSyntax` | 使用 bash 语法解析器检查仓库 Shell 脚本。 | `Command · bash -n` | `python-standard` | `scripts/**/*.sh` | `5s / 30s` | `10s / 60s` |
| `scriptCommentLanguage` | 检查 Python、Shell 注释语言与技术术语符合中文维护规范。 | `Python Check · source.comment-language` | `python-standard、java-build` | `scripts/**/*.py`、`scripts/**/*.sh`、`config/technical-terms.json` | `10s / 60s` | `20s / 120s` |

## 仓库、测试、隐私与安全（6）

完整声明：[`repository-safety.yaml`](repository-safety.yaml)

<!-- gate-file: gates/repository-safety.yaml -->
| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |
|---|---|---|---|---|---|---|
| `repositoryFilePolicy` | 统一检查必需入口、禁止根路径、Git 忽略规则和数据库文件边界。 | `Python Check · repository.repository-file-policy` | `python-standard` | `.gitignore`、`harness/manifest.yaml`、`scripts/checks/repository/check_repository_file_policy.py` | `8s / 30s` | `15s / 60s` |
| `noPythonPlaywrightSkips` | 阻止 Python 与 Playwright 测试使用会产生 skipped 结果的 API。 | `Python Check · repository.no-python-playwright-skips` | `session-detail` | `tests/**/*.py`、`tests/**/*.js`、`tests/**/*.ts` | `8s / 30s` | `15s / 60s` |
| `currentSourcePolicy` | 检查源码只描述当前版本、当前 Harness、桌面视口和有效静态资源。 | `Python Check · repository.current-source-policy` | `python-standard` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`harness/**` | `10s / 60s` | `20s / 120s` |
| `acceptanceCaseMapping` | 检查验收用例表中的 ID 与自动化测试绑定完整一致。 | `Python Check · repository.acceptance-case-mapping` | `无` | `docs/acceptance-cases/**/*.md`、`tests/**/*.py`、`tests/**/*.js` | `15s / 60s` | `30s / 120s` |
| `testDataPolicy` | 确保测试数据受 Git 管理、可复现，并且不依赖个人电脑或真实 Session。 | `Python Check · repository.test-data-policy` | `python-standard、java-src` | `tests/**`、`java/**/src/test/**`、`scripts/checks/repository/check_test_data_policy.py` | `15s / 60s` | `30s / 120s` |
| `secretLikeContent` | 扫描仓库中的密钥、Token 与凭据形态内容。 | `Python Check · security.secret-like-content` | `python-standard` | `tests/**`、`docs/**`、`java/**` | `20s / 90s` | `45s / 180s` |

## Agent、Harness 与 OpenSpec（8）

完整声明：[`harness-governance.yaml`](harness-governance.yaml)

<!-- gate-file: gates/harness-governance.yaml -->
| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |
|---|---|---|---|---|---|---|
| `languagePolicy` | 检查仓库规则、Skill 与 Harness 文本符合中文语言政策。 | `Python Check · repository.language-policy` | `harness` | `AGENTS.md`、`CLAUDE.md`、`skills/**` | `8s / 30s` | `15s / 60s` |
| `protectedRootsSync` | 检查各 Agent 入口声明的受保护路径与共享政策一致。 | `Python Check · agent.protected-roots` | `harness` | `AGENTS.md`、`CLAUDE.md`、`.agents/**` | `8s / 30s` | `15s / 60s` |
| `subagentHandoffProtocol` | 检查 subagent handoff 字段、状态和失败策略在各入口保持一致。 | `Python Check · agent.subagent-handoff` | `harness` | `AGENTS.md`、`CLAUDE.md`、`.agents/**` | `8s / 30s` | `15s / 60s` |
| `doctor` | 只读检查 Harness 依赖、结构与配置是否可用。 | `Command · scripts/harness/doctor.sh` | `python-standard` | `scripts/harness/**/*.sh` | `15s / 60s` | `30s / 120s` |
| `agentPolicySize` | 限制 Agent 入口与共享政策体积，防止规则重新膨胀。 | `Python Check · agent.policy-size` | `harness` | `AGENTS.md`、`CLAUDE.md`、`.codex/config.toml` | `5s / 30s` | `10s / 60s` |
| `skillRegistry` | 检查共享 Skill registry、平台入口与物理目录一致。 | `Python Check · agent.skill-registry` | `harness` | `harness/skill-registry.yaml`、`skills/**`、`.agents/skills/**` | `8s / 30s` | `15s / 60s` |
| `harnessStructure` | 验证 Harness manifest、Skill 链接和目录结构契约。 | `Command · scripts/harness/validate_harness_structure.py` | `harness` | `harness/**`、`scripts/harness/**/*.py` | `8s / 30s` | `15s / 60s` |
| `openspecLayout` | 验证 OpenSpec 目录布局和必需文件。 | `Command · scripts/openspec/validate_layout.py` | `harness` | `openspec/**` | `8s / 30s` | `15s / 60s` |

## Web UI 与浏览器检查（8）

完整声明：[`web-quality.yaml`](web-quality.yaml)

<!-- gate-file: gates/web-quality.yaml -->
| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |
|---|---|---|---|---|---|---|
| `rawInnerhtml` | 阻止 JavaScript 使用未受控的 innerHTML 原始写入。 | `Java Rule · raw-innerhtml` | `session-detail、python-standard、java-src` | `java/web/src/main/resources/static/js/**/*.js`、`config/web-quality-baselines.json`、`tests/**/*.js` | `45s / 180s` | `120s / 600s` |
| `layoutInlineStyle` | 阻止模板或 JavaScript 绕过样式层直接写布局属性。 | `Java Rule · layout-inline-style` | `session-detail、java-src` | `java/web/src/main/resources/static/js/**/*.js`、`java/web/src/main/resources/templates/**/*.html`、`config/web-quality-baselines.json` | `45s / 180s` | `120s / 600s` |
| `templateContract` | 检查 Web 模板不使用遗留标记或不安全的内联交互。 | `Java Rule · template-contract` | `session-detail、java-src` | `java/web/src/main/resources/templates/**`、`java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRule.java`、`java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRuleTest.java` | `30s / 120s` | `90s / 360s` |
| `staticCssContract` | 检查 Web 静态资源加载、CSS 结构与基线契约。 | `Java Rule · static-resource-contract` | `session-detail、java-src` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`java/web/src/main/resources/templates/**/*.html` | `30s / 120s` | `90s / 360s` |
| `cssOwnership` | 检查顶层 CSS 的组件归属、设计变量与选择器边界。 | `Java Rule · css-ownership` | `session-detail、python-standard、java-src` | `java/web/src/main/resources/static/css/**/*.css`、`scripts/gates/executor.py`、`tests/gates/test_executor.py` | `45s / 180s` | `120s / 600s` |
| `webResourceTests` | 运行 Java Web 模板、CSS 与 JavaScript 的资源契约测试。 | `Gradle Task · :java:web:test` | `session-detail、java-src` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`java/web/src/test/java/com/feipi/session/browser/web/page/**` | `60s / 300s` | `180s / 900s` |
| `browserLayout` | 用 Playwright 验证主要页面、布局与视觉壳层契约。 | `Playwright · configured suite` | `session-detail` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` | `90s / 300s` | `240s / 900s` |
| `browserInteraction` | 用 Playwright 验证 Session、列表与迁移页面交互。 | `Playwright · configured suite` | `session-detail` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` | `90s / 300s` | `240s / 900s` |

## Java 构建与源码质量（8）

完整声明：[`java-quality.yaml`](java-quality.yaml)

<!-- gate-file: gates/java-quality.yaml -->
| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |
|---|---|---|---|---|---|---|
| `javaCheck` | 运行 Java 模块编译、单元测试与标准 Gradle 检查。 | `Gradle Task · check` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`**/*.java` | `240s / 900s` | `600s / 1800s` |
| `javaChineseComments` | 检查 Java、Kotlin 与 Gradle 注释符合中文和术语政策。 | `Java Rule · java-comment-language` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`java/**/src/main/kotlin/**/*.kt` | `60s / 300s` | `180s / 900s` |
| `javaRecordComponentJavadocs` | 检查公开 record component 具有匹配的 Javadoc 参数说明。 | `Java Rule · record-component-javadocs` | `java-src` | `java/**/src/main/java/**/*.java`、`**/*.java` | `45s / 180s` | `120s / 600s` |
| `noJavaTestSkips` | 阻止 Java 测试出现 skipped 或 aborted 结果。 | `Gradle Task · verifyNoSkippedJavaTests` | `java-src` | `java/**/src/test/java/**/*.java` | `30s / 180s` | `90s / 600s` |
| `noJavaSuppressWarnings` | 阻止 Java 生产源码新增 PMD 抑制注解。 | `Java Rule · no-pmd-suppressions` | `java-src` | `java/**/src/main/java/**/*.java` | `45s / 180s` | `120s / 600s` |
| `reuseStandardCpd` | 按共享复用政策执行 Java CPD 重复代码检查。 | `Gradle Task · reuseStandardCpd` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` | `120s / 600s` | `420s / 1200s` |
| `reuseAnalyzeIncremental` | 生成 Java 增量复用分析证据并检查政策变更。 | `Gradle Task · reuseAnalyzeIncremental` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` | `120s / 600s` | `420s / 1200s` |
| `javaApiSnapshot` | 比较公开 Java API 与受控快照，防止未审阅的兼容变化。 | `Java Rule · java-api-snapshot` | `java-src、java-build` | `config/api-snapshots/java-public-api.txt`、`java/**/src/main/java/**/*.java` | `90s / 300s` | `240s / 1200s` |

## 产品冒烟（2）

完整声明：[`product-smoke.yaml`](product-smoke.yaml)

<!-- gate-file: gates/product-smoke.yaml -->
| Gate | 作用 | 执行方式 | Target preset | Trigger | 增量目标 | 全量目标 |
|---|---|---|---|---|---|---|
| `scanScriptSmoke` | 验证 session-browser scan 命令与发行 CLI 的进程级契约。 | `Scan Smoke · configured suite` | `scan-script-smoke` | `scripts/session-browser.sh`、`java/app-cli/**`、`java/scan-engine/**` | `90s / 300s` | `180s / 600s` |
| `sessionSamples` | 用合成 Session 样本验证解析、标准化与契约集成。 | `Gradle Task · :java:tests:contracts:sampleIntegrationTest` | `scan-script-smoke` | `tests/fixtures/session_samples/**`、`java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**`、`java/sources/**` | `90s / 300s` | `240s / 900s` |

<!-- GATE-CATALOG:END -->

## 修改规则

1. 先在对应领域 YAML 修改唯一 Gate declaration，不复制同名 Gate。
2. 同时维护 Trigger、Target tag、两套 profile 与各自时效。
3. 同步本页并运行 catalog、planner 与文档 contract。
4. 删除或改名时确认旧 Gate、旧 Check ID、旧 caller 和旧术语零引用，不保留 alias。
5. 最后运行受影响 Gate 和 `python3 scripts/gates/cli.py --mode incremental`。
