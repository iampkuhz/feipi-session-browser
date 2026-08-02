# Gate 精简目录

## 先说结论

Catalog 当前登记 **45 个逻辑 Gate**，但并不是每次都执行 45 个：其中 44 个可进入 `required`，
`javaApiSnapshot` 只属于 `full`。本次实际执行集合按以下顺序决定：

```text
changed path → path_rules 选择 target → Gate 的 target pattern → tier / dominance → 执行计划
```

日常定位时先在本页找到 Gate，再打开该领域 YAML 搜索 Gate 名称。根入口
[`../gates.yaml`](../gates.yaml) 只保存全局 target、路径分类、tier 和分片清单；每条 Gate 的完整命令、
timeout 与 pattern 只在一个分片中声明。`catalog_order` 仅用于保持历史注册顺序，target 内执行先后仍由
各 target 的 `order` 决定。

## 入口缩写

- `java:<rule-id>`：Java quality-gates rule。
- `check:<check-id>`：`python3 -m scripts.checks <check-id>`。
- `gradle:<task>`：Gradle task。
- `command:<name>`：Ruff、Pytest、Playwright 或明确脚本命令。

“主要触发点”只列 1–3 个便于识别的真实 pattern，不复制全部实现路径；完整 pattern 以对应 YAML 为准。
`目标命中即运行` 表示该 Gate 使用 `incremental: always`。

<!-- GATE-CATALOG:START -->

## Python 与脚本工具（11）

完整声明：[`python-tooling.yaml`](python-tooling.yaml)

<!-- gate-file: gates/python-tooling.yaml -->
| Gate | 作用 | 入口 / Owner | Target | 主要触发点 |
|---|---|---|---|---|
| `pythonFormat` | 校验仓库 Python 源码符合 Ruff 格式化结果。 | `command:ruff format` | `python-standard` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonLint` | 检查 Python 静态问题与 import 顺序。 | `command:ruff check` | `python-standard` | `pyproject.toml`、`scripts/**/*.py`、`tests/**/*.py` |
| `pythonCoverage` | 运行 Harness、Gate 与质量契约测试，并生成 scripts 分支覆盖率报告。 | `command:pytest` | `python-standard、acceptance-contracts` | `config/gates/**`、`scripts/gates/executor.py`、`tests/**/*.py` |
| `pythonAudit` | 审计 Python 锁定依赖漏洞与 scripts 中的高危源码。 | `check:repository.python-security` | `python-standard` | `pyproject.toml`、`uv.lock`、`scripts/**/*.py` |
| `pythonComplexity` | 生成 Python 复杂度债务报告，作为不阻断的维护建议。 | `command:radon cc` | `python-standard` | `pyproject.toml`、`scripts/**/*.py` |
| `pythonDeadCode` | 检查 scripts 与测试中的高置信度无引用 Python 代码。 | `command:vulture` | `python-standard` | `scripts/**/*.py`、`tests/**/*.py` |
| `pythonDeps` | 检查 scripts 的 Python 依赖缺失、误用与多余声明。 | `command:deptry` | `python-standard` | `pyproject.toml`、`uv.lock` |
| `bashSyntax` | 使用 bash 语法解析器检查仓库 Shell 脚本。 | `command:bash -n` | `python-standard` | `scripts/**/*.sh` |
| `scriptCommentLanguage` | 检查 Python、Shell 注释语言与技术术语符合中文维护规范。 | `check:source.comment-language` | `python-standard、java-build` | `scripts/**/*.py`、`scripts/**/*.sh`、`config/technical-terms.json` |
| `pythonCompile` | 编译 scripts/checks Python 模块，阻止语法错误。 | `command:compileall` | `session-detail` | `scripts/checks/web/check_session_detail_*.py` |
| `pytest` | 运行 Acceptance Contract 与 Session Detail 的定向 Pytest 契约。 | `command:pytest` | `acceptance-contracts、session-detail` | `docs/acceptance-contracts/**/*.md`、`tests/**/*.py`、`java/web/src/main/resources/static/**` |

## 仓库、测试、隐私与安全（8）

完整声明：[`repository-safety.yaml`](repository-safety.yaml)

<!-- gate-file: gates/repository-safety.yaml -->
| Gate | 作用 | 入口 / Owner | Target | 主要触发点 |
|---|---|---|---|---|
| `ignoredTrackedFiles` | 阻止被 Git 忽略的文件同时进入 tracked index。 | `check:repository.ignored-tracked` | `python-standard` | `.gitignore`、`config/gates/**`、`scripts/gates/**` |
| `misplacedGeneratedPaths` | 检查仓库磁盘上是否出现 manifest 禁止的生成路径。 | `check:repository.misplaced-generated-paths` | `python-standard、acceptance-contracts、session-detail、index、java-src、java-build、scan-script-smoke` | 目标命中即运行 |
| `noTestSkips` | 阻止 Python 与 Playwright 测试新增 skip、skipif 或 fixme。 | `check:repository.no-test-skips` | `acceptance-contracts、session-detail` | `tests/**/*.py`、`tests/**/*.js`、`tests/playwright/playwright.config.js` |
| `repoStructure` | 检查必需维护入口存在，并阻止运行态或数据库文件进入 Git。 | `check:repository.structure` | `python-standard` | `config/gates/**`、`scripts/gates/**`、`scripts/openspec/**` |
| `repoSlimming` | 阻止历史标记、非桌面视口与无效兼容垫片回流仓库。 | `check:repository.repo-slimming` | `python-standard` | `harness/**`、`openspec/**`、`java/web/src/main/resources/static/**/*.css` |
| `acceptanceContracts` | 检查 Acceptance Contract 文档与测试 case 映射完整一致。 | `check:openspec.acceptance-contracts` | `acceptance-contracts` | `docs/acceptance-contracts/**/*.md`、`tests/**/*.py`、`tests/**/*.js` |
| `noRealSessionFixtures` | 阻止真实 Session 内容进入测试、文档或源码 fixture。 | `check:repository.no-real-session-fixtures` | `python-standard` | `tests/**`、`docs/**`、`java/**` |
| `secretLikeContent` | 扫描仓库中的密钥、Token 与凭据形态内容。 | `check:security.secret-like-content` | `python-standard` | `tests/**`、`scripts/**`、`harness/**` |

## Agent、Harness 与 OpenSpec（8）

完整声明：[`harness-governance.yaml`](harness-governance.yaml)

<!-- gate-file: gates/harness-governance.yaml -->
| Gate | 作用 | 入口 / Owner | Target | 主要触发点 |
|---|---|---|---|---|
| `languagePolicy` | 检查仓库规则、Skill 与 Harness 文本符合中文语言政策。 | `check:repository.language-policy` | `harness` | `AGENTS.md`、`skills/**`、`harness/**` |
| `protectedRootsSync` | 检查各 Agent 入口声明的受保护路径与共享政策一致。 | `check:agent.protected-roots` | `harness` | `AGENTS.md`、`config/gates/**`、`.codex/**` |
| `subagentHandoffProtocol` | 检查 subagent handoff 字段、状态和失败策略在各入口保持一致。 | `check:agent.subagent-handoff` | `harness` | `AGENTS.md`、`config/gates/**`、`skills/**` |
| `doctor` | 只读检查 Harness 依赖、结构与配置是否可用。 | `command:doctor.sh` | `python-standard` | `scripts/harness/**/*.sh` |
| `agentPolicySize` | 限制 Agent 入口与共享政策体积，防止规则重新膨胀。 | `check:agent.policy-size` | `harness` | `AGENTS.md`、`CLAUDE.md`、`harness/agent-policy.manifest.yaml` |
| `skillRegistry` | 检查共享 Skill registry、平台入口与物理目录一致。 | `check:agent.skill-registry` | `harness` | `harness/skill-registry.yaml`、`skills/**`、`.codex/skills/**` |
| `harnessStructure` | 验证 Harness manifest、Skill 链接和目录结构契约。 | `command:validate_harness_structure.py` | `harness` | `harness/**`、`scripts/harness/**/*.py` |
| `openspecLayout` | 验证 OpenSpec 目录布局和必需文件。 | `command:validate_layout.py` | `harness` | `openspec/**` |

## Web UI 与浏览器契约（7）

完整声明：[`web-quality.yaml`](web-quality.yaml)

<!-- gate-file: gates/web-quality.yaml -->
| Gate | 作用 | 入口 / Owner | Target | 主要触发点 |
|---|---|---|---|---|
| `rawInnerhtml` | 阻止 JavaScript 使用未受控的 innerHTML 原始写入。 | `java:raw-innerhtml` | `session-detail、acceptance-contracts、python-standard、java-src` | `java/web/src/main/resources/static/js/**/*.js`、`config/web-quality-baselines.json`、`tests/**/*.js` |
| `layoutInlineStyle` | 阻止模板或 JavaScript 绕过样式层直接写布局属性。 | `java:layout-inline-style` | `session-detail、java-src` | `java/web/src/main/resources/static/js/**/*.js`、`java/web/src/main/resources/templates/**/*.html`、`config/web-quality-baselines.json` |
| `templateContract` | 检查 Web 模板不使用遗留标记或不安全的内联交互。 | `java:template-contract` | `session-detail、java-src` | `java/web/src/main/resources/templates/**`、`java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRule.java` |
| `staticCssContract` | 检查 Web 静态资源加载、CSS 结构与基线契约。 | `java:static-resource-contract` | `session-detail、java-src` | `java/web/src/main/resources/static/**/*.css`、`java/web/src/main/resources/static/**/*.js`、`java/web/src/main/resources/templates/**/*.html` |
| `cssOwnership` | 检查顶层 CSS 的组件归属、设计变量与选择器边界。 | `java:css-ownership` | `session-detail、python-standard、acceptance-contracts、java-src` | `java/web/src/main/resources/static/css/**/*.css`、`scripts/gates/executor.py`、`tests/gates/test_executor.py` |
| `browserLayout` | 用 Playwright 验证主要页面、布局与视觉壳层契约。 | `command:playwright` | `session-detail` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` |
| `browserInteraction` | 用 Playwright 验证 Session、列表与迁移页面交互。 | `command:playwright` | `session-detail` | `java/web/src/main/resources/templates/**`、`java/web/src/main/resources/static/**`、`tests/playwright/**` |

## Java 构建与源码质量（8）

完整声明：[`java-quality.yaml`](java-quality.yaml)

<!-- gate-file: gates/java-quality.yaml -->
| Gate | 作用 | 入口 / Owner | Target | 主要触发点 |
|---|---|---|---|---|
| `javaCheck` | 运行 Java 模块编译、单元测试与标准 Gradle 检查。 | `gradle:check` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`java/**/src/test/java/**/*.java`、`gradle/build-logic/**` |
| `javaChineseComments` | 检查 Java、Kotlin 与 Gradle 注释符合中文和术语政策。 | `java:java-comment-language` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`java/**/src/main/kotlin/**/*.kt`、`config/technical-terms.json` |
| `javaRecordComponentJavadocs` | 检查公开 record component 具有匹配的 Javadoc 参数说明。 | `java:record-component-javadocs` | `java-src` | `java/**/src/main/java/**/*.java`、`**/*.java` |
| `noJavaTestSkips` | 阻止 Java 测试出现 skipped 或 aborted 结果。 | `gradle:verifyNoSkippedJavaTests` | `java-src` | `java/**/src/test/java/**/*.java` |
| `noJavaSuppressWarnings` | 阻止 Java 生产源码新增 PMD 抑制注解。 | `java:no-pmd-suppressions` | `java-src` | `java/**/src/main/java/**/*.java` |
| `reuseStandardCpd` | 按共享复用政策执行 Java CPD 重复代码检查。 | `gradle:reuseStandardCpd` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` |
| `reuseAnalyzeIncremental` | 生成 Java 增量复用分析证据并检查政策变更。 | `gradle:reuseAnalyzeIncremental` | `java-src、java-build` | `java/**/src/main/java/**/*.java`、`config/reuse-policy/**`、`java/**/build.gradle.kts` |
| `javaApiSnapshot` | 比较公开 Java API 与受控快照，防止未审阅的兼容变化。 | `java:java-api-snapshot` | `java-src、java-build` | `config/api-snapshots/java-public-api.txt`、`java/**/src/main/java/**/*.java` |

## 索引与产品冒烟（3）

完整声明：[`product-smoke.yaml`](product-smoke.yaml)

<!-- gate-file: gates/product-smoke.yaml -->
| Gate | 作用 | 入口 / Owner | Target | 主要触发点 |
|---|---|---|---|---|
| `indexIntegrity` | 检查本地 Session 索引文件、表结构与关键字段完整性。 | `check:repository.index-integrity` | `index` | `scripts/checks/repository/check_index_integrity.py` |
| `scanScriptSmoke` | 验证 session-browser scan 命令与发行 CLI 的进程级契约。 | `command:pytest` | `scan-script-smoke` | `scripts/session-browser.sh`、`java/app-cli/**`、`tests/script_commands/**` |
| `sessionSamples` | 用合成 Session 样本验证解析、标准化与契约集成。 | `gradle:java:tests:contracts:sampleIntegrationTest` | `scan-script-smoke` | `tests/fixtures/session_samples/**`、`java/sources/**`、`java/normalization-engine/**` |

<!-- GATE-CATALOG:END -->

## 修改规则

1. 在一个领域 YAML 中新增、修改或删除完整 Gate declaration。
2. 新增 Gate 时分配一个唯一 `catalog_order`；现有值按 10 留出插入空间，删除时不必重排其他 Gate。
3. 同批更新本页；“作用”必须与 catalog `description` 完全相同。
4. 运行 catalog/documentation contracts、受影响 target 和最终 required Gate。
5. 删除或迁移时确认旧名称、owner、命令和路径引用为零，不保留 alias 或 wrapper。
