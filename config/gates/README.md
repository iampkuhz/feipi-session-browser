# Gate 精简目录

## 先说结论

Catalog v6 当前登记 **44 个逻辑 Gate**。从 typed catalog 运行时计算，**42 个可进入 `required`**；
`pythonDependencyVulnerabilities` 与 `javaApiSnapshot` 仅在 `full` tier 才具备成员资格。前者是联网依赖
漏洞审计（网络不可用为 `BLOCKED`），后者检查 Java 公开 API 快照。
这里的“可进入”表示 tier 成员资格，不表示每次变更都会触发或已经通过。

`target` 是由 changed path 激活的、可多选且有序的**验证场景**。一个路径可以同时选择多个 target，
一个 Gate 也可以服务多个 target；target 不是 owner、executor、tier 或 Gate 的唯一分类。计划严格按以下顺序形成：

```text
changed path → path rule.targets → Gate target rule（order + pattern）→ tier 过滤 → plan
```

例如修改 `tests/gates/test_planner.py` 会由 test path rule 同时激活 `acceptance-contracts` 与
`python-standard`，再分别按 Gate 的对应 target pattern 选 Gate；修改 `tests/ui/test_web_static_contract.py`
会激活 `session-detail`、`acceptance-contracts` 与 `python-standard`，UI 测试因此不是一个名为“UI”的
唯一分类。Catalog 声明的 target dominance 只处理显式包含关系，不抹掉其他业务场景。

日常定位时先在本页找到 Gate，再打开该领域 YAML 搜索 Gate 名称。根入口
[`../gates.yaml`](../gates.yaml) 保存 v6 `gate_defaults`、全局 target、path rule、target trigger 与分片清单；
每条 Gate 的 `description`、`targets[].order/patterns`、typed `run` 和显式默认覆盖只在一个分片中声明。
本页不复制完整命令。

## 实现入口与执行通道

两列含义必须分开：

- **实现入口**直接从 typed `run` 派生：`java-rule:<rule-id>`、`gradle-task:<task>`、
  `python-check:<check-id>`、`tool:<tool-or-script>` 或 `suite:<test-suite>`；它回答“实现在哪里”。
- **执行通道**只取 `gradle` 或 `process`：`java-rule`/`gradle-task` 经聚合 Gradle group 执行，其余 typed
  run 经 bounded process 执行；`scan-smoke` 的 Gradle prerequisite 不会把其 Pytest suite 入口改写成 owner。
- `command` 是 typed run kind，不是 owner；executor 只执行冻结计划，也不是规则 owner。

“主要触发点”只展示 1–3 个真实 Gate target pattern；`Target 命中即运行` 表示该 Gate 在相应 target
下的 pattern 为空。完整 target 顺序和 pattern 以对应 YAML 为准。

## Pytest 的唯一归属

| Gate | 唯一执行范围 | 不负责 |
|---|---|---|
| `pythonHarnessTests` | `tests/harness`、`tests/gates`、`tests/checks`、`tests/quality`、`tests/misc`、`tests/test_*.py` | `tests/ui`、scan 进程冒烟 |
| `sessionDetailStaticTests` | 整个 `tests/ui` | Harness/Gate 单测、Playwright |
| `scanScriptSmoke` | `tests/script_commands/test_session_browser_scan_smoke.py` | 普通 Python 单测 |

`acceptanceContracts` 只校验文档与 `contract_case` marker 的映射，不是第四个 Pytest runner。
Playwright suite 由 `browserLayout`/`browserInteraction` 负责，也不放进上述 Pytest 命令。这样每个 Python
测试只有一个执行 Gate；新增测试时先放进对应目录，不要再新增一层“转调测试框架”的包装测试。

<!-- GATE-CATALOG:START -->

## Python 与脚本工具（10）

完整声明：[`python-tooling.yaml`](python-tooling.yaml)

<!-- gate-file: gates/python-tooling.yaml -->
| Gate | 作用 | 实现入口 | 执行通道 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|---|
| `pythonFormat` | 校验仓库 Python 源码符合 Ruff 格式化结果。 | `tool:ruff format` | `process` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonLint` | 检查 Python 静态问题与 import 顺序。 | `tool:ruff check` | `process` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonHarnessTests` | 运行 Harness、Gate 与质量契约的固定 Pytest 单测集合。 | `suite:python-harness-tests` | `process` | `python-standard` | `required` | `pyproject.toml`、`config/gates.yaml`、`config/gates/**` |
| `pythonSourceSecurity` | 使用 Bandit 对 scripts Python 源码执行离线安全扫描。 | `tool:bandit` | `process` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py` |
| `pythonDependencyVulnerabilities` | 审计 Python 锁定依赖中的已知漏洞。 | `python-check:repository.python-dependency-vulnerabilities` | `process` | `python-standard` | `full` | `pyproject.toml`、`uv.lock` |
| `pythonDeadCode` | 检查 scripts 与测试中的高置信度无引用 Python 代码。 | `tool:vulture` | `process` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonDependencyDeclarations` | 检查 scripts 的 Python 依赖声明完整性。 | `tool:deptry` | `process` | `python-standard` | `required` | `pyproject.toml`、`scripts/**/*.py` |
| `bashSyntax` | 使用 bash 语法解析器检查仓库 Shell 脚本。 | `tool:bash -n` | `process` | `python-standard` | `quick` | `scripts/**/*.sh` |
| `scriptCommentLanguage` | 检查 Python、Shell 注释语言与技术术语符合中文维护规范。 | `python-check:source.comment-language` | `process` | `python-standard、java-build` | `required` | `scripts/**/*.py`、`scripts/**/*.sh`、`config/technical-terms.json` |
| `sessionDetailStaticTests` | 运行 Web 静态资源的固定 Pytest 契约。 | `suite:session-detail-static-tests` | `process` | `session-detail` | `required` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/ui/**/*.py` |

## 仓库、测试、隐私与安全（8）

完整声明：[`repository-safety.yaml`](repository-safety.yaml)

<!-- gate-file: gates/repository-safety.yaml -->
| Gate | 作用 | 实现入口 | 执行通道 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|---|
| `ignoredTrackedFiles` | 阻止被 Git 忽略的文件同时进入 tracked index。 | `python-check:repository.ignored-tracked` | `process` | `python-standard` | `required` | `.gitignore`、`scripts/checks/repository/check_ignored_tracked_files.py`、`scripts/gates/**` |
| `misplacedGeneratedPaths` | 检查仓库磁盘上是否出现 manifest 禁止的生成路径。 | `python-check:repository.misplaced-generated-paths` | `process` | `python-standard、acceptance-contracts、session-detail、index、java-src、java-build、scan-script-smoke` | `required` | Target 命中即运行 |
| `noTestSkips` | 阻止 Python 与 Playwright 测试新增 skip、skipif 或 fixme。 | `python-check:repository.no-test-skips` | `process` | `acceptance-contracts、session-detail` | `quick` | `tests/**/*.py`、`tests/**/*.js`、`tests/**/*.ts` |
| `repoStructure` | 检查必需维护入口存在，并阻止运行态或数据库文件进入 Git。 | `python-check:repository.structure` | `process` | `python-standard` | `quick` | `scripts/checks/repository/check_repo_structure.py`、`scripts/gates/**`、`scripts/openspec/**` |
| `repoSlimming` | 阻止历史标记、非桌面视口与无效兼容垫片回流仓库。 | `python-check:repository.repo-slimming` | `process` | `python-standard` | `required` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`harness/**` |
| `acceptanceContracts` | 检查 Acceptance Contract 文档与测试 case 映射完整一致。 | `python-check:openspec.acceptance-contracts` | `process` | `acceptance-contracts` | `required` | `docs/acceptance-contracts/**/*.md`、`tests/**/*.py`、`tests/**/*.js` |
| `noRealSessionFixtures` | 阻止真实 Session 内容进入测试、文档或源码 fixture。 | `python-check:repository.no-real-session-fixtures` | `process` | `python-standard` | `required` | `tests/**`、`docs/**`、`java/**` |
| `secretLikeContent` | 扫描仓库中的密钥、Token 与凭据形态内容。 | `python-check:security.secret-like-content` | `process` | `python-standard` | `required` | `tests/**`、`docs/**`、`java/**` |

## Agent、Harness 与 OpenSpec（8）

完整声明：[`harness-governance.yaml`](harness-governance.yaml)

<!-- gate-file: gates/harness-governance.yaml -->
| Gate | 作用 | 实现入口 | 执行通道 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|---|
| `languagePolicy` | 检查仓库规则、Skill 与 Harness 文本符合中文语言政策。 | `python-check:repository.language-policy` | `process` | `harness` | `quick` | `AGENTS.md`、`CLAUDE.md`、`skills/**` |
| `protectedRootsSync` | 检查各 Agent 入口声明的受保护路径与共享政策一致。 | `python-check:agent.protected-roots` | `process` | `harness` | `quick` | `AGENTS.md`、`CLAUDE.md`、`.agents/**` |
| `subagentHandoffProtocol` | 检查 subagent handoff 字段、状态和失败策略在各入口保持一致。 | `python-check:agent.subagent-handoff` | `process` | `harness` | `quick` | `AGENTS.md`、`CLAUDE.md`、`.agents/**` |
| `doctor` | 只读检查 Harness 依赖、结构与配置是否可用。 | `tool:scripts/harness/doctor.sh` | `process` | `python-standard` | `quick` | `scripts/harness/**/*.sh` |
| `agentPolicySize` | 限制 Agent 入口与共享政策体积，防止规则重新膨胀。 | `python-check:agent.policy-size` | `process` | `harness` | `required` | `AGENTS.md`、`CLAUDE.md`、`.codex/config.toml` |
| `skillRegistry` | 检查共享 Skill registry、平台入口与物理目录一致。 | `python-check:agent.skill-registry` | `process` | `harness` | `required` | `harness/skill-registry.yaml`、`skills/**`、`.agents/skills/**` |
| `harnessStructure` | 验证 Harness manifest、Skill 链接和目录结构契约。 | `tool:scripts/harness/validate_harness_structure.py` | `process` | `harness` | `quick` | `harness/**`、`scripts/harness/**/*.py` |
| `openspecLayout` | 验证 OpenSpec 目录布局和必需文件。 | `tool:scripts/openspec/validate_layout.py` | `process` | `harness` | `required` | `openspec/**` |

## Web UI 与浏览器契约（7）

完整声明：[`web-quality.yaml`](web-quality.yaml)

<!-- gate-file: gates/web-quality.yaml -->
| Gate | 作用 | 实现入口 | 执行通道 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|---|
| `rawInnerhtml` | 阻止 JavaScript 使用未受控的 innerHTML 原始写入。 | `java-rule:raw-innerhtml` | `gradle` | `session-detail、acceptance-contracts、python-standard、java-src` | `required` | `java/web/src/main/resources/static/js/**/*.js`、`config/web-quality-baselines.json`、`tests/**/*.js` |
| `layoutInlineStyle` | 阻止模板或 JavaScript 绕过样式层直接写布局属性。 | `java-rule:layout-inline-style` | `gradle` | `session-detail、java-src` | `required` | `java/web/src/main/resources/static/js/**/*.js`、`java/web/src/main/resources/templates/**/*.html`、`config/web-quality-baselines.json` |
| `templateContract` | 检查 Web 模板不使用遗留标记或不安全的内联交互。 | `java-rule:template-contract` | `gradle` | `session-detail、java-src` | `required` | `java/web/src/main/resources/templates/**`、`java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRule.java`、`java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRuleTest.java` |
| `staticCssContract` | 检查 Web 静态资源加载、CSS 结构与基线契约。 | `java-rule:static-resource-contract` | `gradle` | `session-detail、java-src` | `required` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`java/web/src/main/resources/templates/**/*.html` |
| `cssOwnership` | 检查顶层 CSS 的组件归属、设计变量与选择器边界。 | `java-rule:css-ownership` | `gradle` | `session-detail、python-standard、acceptance-contracts、java-src` | `required` | `java/web/src/main/resources/static/css/**/*.css`、`scripts/gates/executor.py`、`tests/gates/test_executor.py` |
| `browserLayout` | 用 Playwright 验证主要页面、布局与视觉壳层契约。 | `suite:playwright` | `process` | `session-detail` | `required` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` |
| `browserInteraction` | 用 Playwright 验证 Session、列表与迁移页面交互。 | `suite:playwright` | `process` | `session-detail` | `required` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` |

## Java 构建与源码质量（8）

完整声明：[`java-quality.yaml`](java-quality.yaml)

<!-- gate-file: gates/java-quality.yaml -->
| Gate | 作用 | 实现入口 | 执行通道 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|---|
| `javaCheck` | 运行 Java 模块编译、单元测试与标准 Gradle 检查。 | `gradle-task:check` | `gradle` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`**/*.java` |
| `javaChineseComments` | 检查 Java、Kotlin 与 Gradle 注释符合中文和术语政策。 | `java-rule:java-comment-language` | `gradle` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`java/**/src/main/kotlin/**/*.kt` |
| `javaRecordComponentJavadocs` | 检查公开 record component 具有匹配的 Javadoc 参数说明。 | `java-rule:record-component-javadocs` | `gradle` | `java-src` | `required` | `java/**/src/main/java/**/*.java`、`**/*.java` |
| `noJavaTestSkips` | 阻止 Java 测试出现 skipped 或 aborted 结果。 | `gradle-task:verifyNoSkippedJavaTests` | `gradle` | `java-src` | `quick` | `java/**/src/test/java/**/*.java` |
| `noJavaSuppressWarnings` | 阻止 Java 生产源码新增 PMD 抑制注解。 | `java-rule:no-pmd-suppressions` | `gradle` | `java-src` | `quick` | `java/**/src/main/java/**/*.java` |
| `reuseStandardCpd` | 按共享复用政策执行 Java CPD 重复代码检查。 | `gradle-task:reuseStandardCpd` | `gradle` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` |
| `reuseAnalyzeIncremental` | 生成 Java 增量复用分析证据并检查政策变更。 | `gradle-task:reuseAnalyzeIncremental` | `gradle` | `java-src、java-build` | `required` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` |
| `javaApiSnapshot` | 比较公开 Java API 与受控快照，防止未审阅的兼容变化。 | `java-rule:java-api-snapshot` | `gradle` | `java-src、java-build` | `full` | `config/api-snapshots/java-public-api.txt`、`java/**/src/main/java/**/*.java` |

## 索引与产品冒烟（3）

完整声明：[`product-smoke.yaml`](product-smoke.yaml)

<!-- gate-file: gates/product-smoke.yaml -->
| Gate | 作用 | 实现入口 | 执行通道 | Target | Tier | 主要触发点 |
|---|---|---|---|---|---|---|
| `indexIntegrity` | 检查本地 Session 索引文件、表结构与关键字段完整性。 | `python-check:repository.index-integrity` | `process` | `index` | `required` | `scripts/checks/repository/check_index_integrity.py` |
| `scanScriptSmoke` | 验证 session-browser scan 命令与发行 CLI 的进程级契约。 | `suite:scan-script-smoke` | `process` | `scan-script-smoke` | `required` | `scripts/session-browser.sh`、`java/app-cli/**`、`java/scan-engine/**` |
| `sessionSamples` | 用合成 Session 样本验证解析、标准化与契约集成。 | `gradle-task::java:tests:contracts:sampleIntegrationTest` | `gradle` | `scan-script-smoke` | `required` | `tests/fixtures/session_samples/**`、`java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**`、`java/sources/**` |

<!-- GATE-CATALOG:END -->

## 阅读与修改规则

1. 先读 [`../gates.yaml`](../gates.yaml) 的 v6 root schema：`version`、`gate_defaults`、`targets`、
   `gate_files`、`path_rules` 与 `target_triggers` 都是 exact-key/exact-type；默认值只允许来自
   `gate_defaults`，identity、routing、pattern、order 与 run 不得默认。
2. 在一个领域分片中新增、修改或删除 Gate。每条 Gate 必须显式写 `name`、`description`、`targets`
   和一个 discriminated `run`；每个 target rule 必须写 `name`、`order`、`patterns`，不接受 v6 schema
   未声明的兼容字段或旧式嵌套结构。
3. 根据唯一实现选择 run kind：`java-rule`、`gradle-task`、`python-check`、`command`、`playwright` 或
   `scan-smoke`；公共 `minimum_tier`、`timeout`、`changed_files`、`network_failure` 只有偏离
   `gate_defaults` 时才显式覆盖。
4. 同批更新本页；作用必须等于 catalog `description`，实现入口和执行通道必须从 typed run 派生，
   trigger 示例必须来自真实 pattern。不要复制完整 argv。
5. 运行 catalog/documentation contracts、受影响 target 和最终 required Gate。删除或迁移时确认旧 Gate 名、
   旧字段、实现和 caller 零引用，不保留 alias、wrapper 或兼容术语。
