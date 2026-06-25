# Python-Java 职责边界地图

> 生成时间：2026-06-25
> 分支：main_java
> 状态：Phase 0+1 已完成，产品运行时全部走 Java CLI

---

## 1. 职责表

| # | 功能 | 当前实现 | 目标 Java-first 状态 | 风险 | 验证方式 |
|---|------|----------|---------------------|------|----------|
| 1 | CLI 入口（scan/serve/stop/version/help） | **Java** — `java/app-cli` 通过 `scripts/session-browser.sh` 路由到 Java launcher | 已完成 | 低 | `./scripts/session-browser.sh version` 输出非空 |
| 2 | 会话扫描（全量/增量） | **Java** — `java/scan-engine` (FullScanEngine, IncrementalScanEngine, BackgroundScanner) | 已完成 | 低 | `./scripts/session-browser.sh scan` 正常执行 |
| 3 | 源适配器（Claude/Codex/Qoder） | **Java** — `java/source-claude`, `java/source-codex`, `java/source-qoder` 实现 `SourceAdapter` SPI | 已完成 | 低 | `java/source-spi` 接口 + contract-tests 覆盖 |
| 4 | JSONL 读取 | **Java** — `java/source-json` (JsonlReader, JsonSourceRecordMapper) | 已完成 | 低 | unit tests in `java/source-json` |
| 5 | 归一化引擎 | **Java** — `java/normalization-engine` (NormalizationEngine, EventClassifier, TokenAccountant) | 已完成 | 低 | unit tests + contract-tests |
| 6 | SQLite 索引 | **Java** — `java/index-sqlite` (IndexSchema, SessionQueryRepository, AggregateQueryRepository, MigrationRunner) | 已完成 | 低 | unit tests in `java/index-sqlite` |
| 7 | 查询 API | **Java** — `java/query-api` (Sort, PageRequest, 各类 Filter) | 已完成 | 低 | unit tests in `java/query-api` |
| 8 | 应用层用例 | **Java** — `java/application` (DashboardUseCase, SessionListUseCase, SessionDetailUseCase, ProjectListUseCase, DiagnosticsUseCase) | 已完成 | 低 | unit tests in `java/application` |
| 9 | Web 服务与页面渲染 | **Java** — `java/web` (WebServer, Pebble 模板, CSS/JS 静态资源, API handler) | 已完成 | 中 | `./scripts/session-browser.sh serve` + 浏览器验证 |
| 10 | Normalized artifact 写入 | **Java** — `java/artifact-normalized` (NormalizedArtifactWriter, CanonicalJsonWriter) | 已完成 | 低 | unit tests in `java/artifact-normalized` |
| 11 | 代码复用分析 | **Java** — `java/reuse-analyzer` (SpoonAnalyzer, Fingerprinter, OwnershipClassifier) | 已完成 | 低 | unit tests in `java/reuse-analyzer` |
| 12 | Token Attribution 引擎 | **Python** — `src/session_browser/attribution/` (~31K LOC, 145 文件) | **待迁移** — 需移植为 Java 模块 | **高** — 这是 Python 层最大且最复杂的残留模块 | attribution 单元测试覆盖率 + 对比 Java/Python 输出一致性 |
| 13 | 旧 domain 模型 | **Python** — `src/session_browser/domain/` (~20 文件) | **待删除** — 被 attribution 引用；attribution 迁移后一并删除 | 中 | 确认无其他 Python 调用者后删除 |
| 14 | 旧 web 模板与渲染器 | **Python** — `src/session_browser/web/` (~30 文件 + Jinja2 模板) | **待删除** — Java `java/web` 已完整接管 | 低 | 确认 `scripts/session-browser.sh` 无 Python web 调用路径 |
| 15 | 旧 Python CLI | **Python** — `src/session_browser/cli.py` (67 行, 已标记退休) | **待删除** — 仅打印提示信息，无实际功能 | 低 | `python -m session_browser` 输出提示信息即可确认 |
| 16 | Python 配置工具 | **Python** — `src/session_browser/config.py` (77 行) | **待删除** — 被 attribution 和 cli 引用 | 低 | 随 cli.py 和 attribution 一并移除 |
| 17 | Shell 开发工具链（format/lint/type/quality） | **Shell + Python scripts** — `scripts/session-browser.sh` 中 format/lint/type/coverage/audit 等 | **暂保留** — 这些是仓库质量工具，非产品运行时 | 低 | `./scripts/session-browser.sh format-check` |
| 18 | Shell 质量门禁脚本 | **Python** — `scripts/quality/*.py` (~40 文件) | **暂保留** — 仓库开发工具，不属于产品迁移范围 | 低 | `./scripts/session-browser.sh quality` |
| 19 | OpenSpec 脚本 | **Python** — `scripts/openspec/*.py` (4 文件) | **暂保留** — 仓库开发工具 | 低 | 脚本独立运行 |
| 20 | Harness 脚本 | **Python** — `scripts/harness/*.py` (~10 文件) | **暂保留** — 仓库开发工具 | 低 | 脚本独立运行 |
| 21 | Agent hooks | **Python** — `scripts/agent_hooks/*.py`, `scripts/claude_hooks/**/*.py` | **暂保留** — Claude Code hook 机制依赖 Python | 低 | hook 触发验证 |
| 22 | Python 测试 | **Python** — `tests/` (~83 测试文件) | **不确定** — 部分测试验证旧 Python web/domain，应随代码删除；部分测试验证 scripts/ 工具应保留 | 中 | 需逐个分类 tests/ 下测试归属 |

---

## 2. Python 暂保留清单

以下功能当前仍由 Python 承担，且不在本次迁移的直接范围内：

### 2.1 产品功能（待迁移）

| 模块 | 路径 | 文件数 | 估算 LOC | 说明 |
|------|------|--------|----------|------|
| Token Attribution 引擎 | `src/session_browser/attribution/` | ~100 | ~30,000 | 核心分析功能：token 归因、API family 归一化、usage 估算、span 构建、多 agent 支持 (Claude Code / Codex / Qoder) |
| 旧 domain 模型 | `src/session_browser/domain/` | ~20 | ~2,000 | 被 attribution 引用的领域模型；attribution 迁移后删除 |
| 旧 web 层 | `src/session_browser/web/` | ~25 | ~3,000 | Jinja2 模板 + 渲染器；Java web 已接管，待确认无引用后删除 |
| CLI + config | `src/session_browser/cli.py`, `config.py`, `__main__.py` | 3 | ~150 | 已退休，仅打印提示信息 |

### 2.2 仓库工具（暂不迁移）

| 类别 | 路径 | 文件数 | 说明 |
|------|------|--------|------|
| 质量门禁 | `scripts/quality/*.py` | ~40 | Ruff、Pyright、Coverage、pip-audit、Bandit 等封装 |
| OpenSpec 工具 | `scripts/openspec/*.py` | 4 | Change 校验、schema 校验、布局校验 |
| Harness 工具 | `scripts/harness/*.py` | ~10 | Agent 运行校验、context 路由校验 |
| Agent hooks | `scripts/agent_hooks/*.py`, `scripts/claude_hooks/**/*.py` | ~10 | Claude Code 生命周期 hook |
| QA 脚本 | `scripts/qa/**/*.py` | ~15 | UI 契约检查、DOM 验证 |
| 辅助脚本 | `scripts/*.py` | ~10 | fixture 生成、CSS 检查、UI 密度检查 |
| Python 测试 | `tests/` | ~83 | 需分类：部分随 Python 产品删除，部分验证 scripts/ 工具保留 |

---

## 3. Java 接管清单

以下功能已完全由 Java 实现并通过 `scripts/session-browser.sh` 或 Java 模块直接使用：

| 功能 | Java 模块 | 关键类 | 验证方式 |
|------|-----------|--------|----------|
| CLI 命令路由 | `java/app-cli` | App, ScanCommand, ServeCommand, StopCommand, VersionCommand, HelpCommand, StatusCommand, QualityCommand, DoctorCommand, DepsCommand, ReleaseCommand, TestCommand | `./scripts/session-browser.sh --help` |
| 源发现与解析 | `java/source-claude`, `java/source-codex`, `java/source-qoder`, `java/source-json` | ClaudeSourceAdapter, CodexSourceAdapter, QoderSourceAdapter, JsonlReader | 各模块 unit tests |
| 源适配器 SPI | `java/source-spi` | SourceAdapter, SourceRoot, Candidate, SourceResult | 接口定义 + contract-tests |
| 归一化 | `java/normalization-engine` | NormalizationEngine, EventClassifier, TokenAccountant, CallBuilder | unit tests |
| 归一化产物写入 | `java/artifact-normalized` | `NormalizedArtifactWriter`, `CanonicalJsonWriter` | 单元测试 |
| 领域模型 | `java/core-domain` | NormalizedCall, NormalizedSessionArtifact, SourceRecord, 枚举类 | 编译验证 |
| SQLite 索引 | `java/index-sqlite` | IndexSchema, IndexConnection, SessionQueryRepository, AggregateQueryRepository, MigrationRunner, PayloadLookup | unit tests |
| 查询接口 | `java/query-api` | Sort, PageRequest, PageResult, 各类 Filter (Title, Model, Agent, Anomaly, Trend) | unit tests |
| 应用用例 | `java/application` | DashboardUseCase, SessionListUseCase, SessionDetailUseCase, ProjectListUseCase, DiagnosticsUseCase, QueryCompositionRoot | unit tests |
| Web 服务 | `java/web` | WebServer, Pebble 模板渲染, 静态资源 (CSS/JS/images), API handler | `./scripts/session-browser.sh serve` + 浏览器验证 |
| 扫描引擎 | `java/scan-engine` | FullScanEngine, IncrementalScanEngine, BackgroundScanner, ScanLock, FingerprintRepository | unit tests |
| 代码复用分析 | `java/reuse-analyzer` | SpoonAnalyzer, Fingerprinter, OwnershipClassifier | unit tests |
| 架构约束测试 | `java/architecture-tests` | 架构规则测试 | `./gradlew :java:architecture-tests:test` |
| 契约测试 | `java/contract-tests` | 跨模块契约绑定 | `./gradlew :java:contract-tests:test` |
| 测试辅助 | `java/test-support` | 共享测试 fixtures 和 utilities | 被其他模块引用 |

---

## 4. 迁移优先级与路线图建议

### P0 — 最大价值、最高复杂度

- **Token Attribution 引擎迁移**（`src/session_browser/attribution/` -> 新 Java 模块 `java/attribution-engine`）
  - 这是 Python 层唯一仍在产品运行时中承担核心业务功能的模块
  - 约 30K LOC，涵盖 5 个 API family、3 种 agent、tokenization 路由
  - 建议分阶段：先迁移 core models + contracts，再迁移各 API family normalizer，最后迁移 collectors
  - 验证策略：Java 输出与 Python 输出进行 golden file 对比

### P1 — 清理删除（低复杂度）

- 删除 `src/session_browser/web/`（Java web 已完全接管）
- 删除 `src/session_browser/cli.py`, `__main__.py`, `config.py`（已退休）
- 删除 `src/session_browser/domain/`（在 attribution 迁移完成后）
- 分类 `tests/`：删除旧 Python 产品测试，保留 scripts/ 工具测试

### P2 — 暂不迁移

- `scripts/` 下的 Python 开发工具（质量门禁、OpenSpec、harness、hooks）
  - 这些是仓库基础设施，不属于产品运行时
  - 除非有明确的 Java 替代方案需求，否则保持现状

---

## 5. 不确定项（不猜测）

| 项 | 说明 |
|----|------|
| Attribution 引擎是否有外部调用者 | 需确认除 scan 流程外是否有其他入口调用 attribution |
| `tests/` 测试文件归属 | 83 个测试文件中，哪些验证产品功能（应删除）、哪些验证工具脚本（应保留），需逐个分类 |
| Attribution 迁移是否需要保留 Python 并行运行 | 取决于是否需要灰度过渡期 |
| `scripts/generate_fixture_sessions.py` 等 fixture 生成脚本 | 是否在 Java 测试中已有等价 fixture 机制，需确认 |
