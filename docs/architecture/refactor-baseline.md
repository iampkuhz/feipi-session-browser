# Java architecture refactor baseline audit

Repository root: `/Users/zhehan/Documents/tools/llm/feipi-session-browser-java`
Task source: `.qoder/task-packs/feipi-java-architecture/tasks/01_baseline_architecture_audit.md`
Generated before any refactor by Task 01 / `feipi-arch-auditor`.

## 1. Branch and dirty status

- Current branch: `main_java`
- Dirty status before creating this report: dirty
- This task writes only `docs/architecture/refactor-baseline.md`; the dirty paths below were present before the report file was created.

`git status --short` output captured before report creation:

```text
A  .agents/skills/feipi-java-feature-dev
A  .agents/skills/feipi-mhtml-export-dev
A  .agents/skills/feipi-privacy-redaction-dev
A  .agents/skills/feipi-quality-gate-diagnosis
A  .agents/skills/feipi-session-detail-ui-dev
A  .agents/skills/feipi-session-ingestion-dev
A  .claude/agents/java-backend-implementer.md
A  .claude/agents/mhtml-export-specialist.md
A  .claude/agents/privacy-reviewer.md
M  .claude/agents/qa-verifier.md
A  .claude/agents/quality-gate-diagnoser.md
A  .claude/agents/session-ingestion-specialist.md
A  .claude/agents/ui-implementation-specialist.md
 M .claude/hooks/post-bash.sh
M  .claude/hooks/stop.sh
M  .claude/settings.json
M  .claude/settings.local.example.json
A  .claude/skills/feipi-java-feature-dev
A  .claude/skills/feipi-mhtml-export-dev
A  .claude/skills/feipi-privacy-redaction-dev
A  .claude/skills/feipi-quality-gate-diagnosis
A  .claude/skills/feipi-session-detail-ui-dev
A  .claude/skills/feipi-session-ingestion-dev
A  .codex/agents/java-backend-implementer.toml
M  .codex/agents/mhtml-export-specialist.toml
A  .codex/agents/privacy-reviewer.toml
M  .codex/agents/qa-verifier.toml
A  .codex/agents/quality-gate-diagnoser.toml
A  .codex/agents/session-ingestion-specialist.toml
A  .codex/agents/ui-implementation-specialist.toml
M  .codex/hooks/stop_check.sh
M  .codex/model-instructions.md
A  .codex/skills/feipi-java-feature-dev
A  .codex/skills/feipi-mhtml-export-dev
A  .codex/skills/feipi-privacy-redaction-dev
A  .codex/skills/feipi-quality-gate-diagnosis
A  .codex/skills/feipi-session-detail-ui-dev
A  .codex/skills/feipi-session-ingestion-dev
 M .gitignore
 M .qoder/hooks/post_bash_guard.sh
M  .qoder/hooks/stop_check.sh
M  AGENTS.md
M  CLAUDE.md
A  docs/agent-runtime.md
A  harness/agent-policy.manifest.yaml
A  harness/agent-runtime-report.schema.json
M  harness/agent-runtime.manifest.yaml
A  harness/skill-registry.yaml
M  scripts/harness/doctor.sh
A  scripts/harness/write_agent_runtime_report.py
A  scripts/quality/check_agent_entry_parity.py
A  scripts/quality/check_agent_permission_policy.py
A  scripts/quality/check_agent_policy_size.py
A  scripts/quality/check_agent_rules_sync.py
M  scripts/quality/check_agent_runtime_manifest.py
A  scripts/quality/check_agent_runtime_report.py
A  scripts/quality/check_no_committed_local_paths.py
A  scripts/quality/check_no_real_session_fixtures.py
A  scripts/quality/check_secret_like_content.py
A  scripts/quality/check_skill_registry.py
M  scripts/quality/quality_targets.py
M  scripts/quality/run_quality_gate.py
A  skills/authoring/feipi-java-feature-dev/SKILL.md
A  skills/authoring/feipi-java-feature-dev/references/java-boundaries.md
A  skills/authoring/feipi-java-feature-dev/references/scope.md
A  skills/authoring/feipi-java-feature-dev/templates/handoff.md
A  skills/authoring/feipi-java-feature-dev/templates/report.md
A  skills/authoring/feipi-mhtml-export-dev/SKILL.md
A  skills/authoring/feipi-mhtml-export-dev/references/export-contract.md
A  skills/authoring/feipi-mhtml-export-dev/references/offline-resource-contract.md
A  skills/authoring/feipi-mhtml-export-dev/references/scope.md
A  skills/authoring/feipi-mhtml-export-dev/references/security-contract.md
A  skills/authoring/feipi-mhtml-export-dev/templates/handoff.md
A  skills/authoring/feipi-mhtml-export-dev/templates/report.md
A  skills/authoring/feipi-privacy-redaction-dev/SKILL.md
A  skills/authoring/feipi-privacy-redaction-dev/references/fixture-policy.md
A  skills/authoring/feipi-privacy-redaction-dev/references/redaction-policy.md
A  skills/authoring/feipi-privacy-redaction-dev/references/scope.md
A  skills/authoring/feipi-privacy-redaction-dev/references/sensitive-fields.md
A  skills/authoring/feipi-privacy-redaction-dev/templates/handoff.md
A  skills/authoring/feipi-privacy-redaction-dev/templates/report.md
A  skills/authoring/feipi-quality-gate-diagnosis/SKILL.md
A  skills/authoring/feipi-quality-gate-diagnosis/references/failure-diagnosis.md
A  skills/authoring/feipi-quality-gate-diagnosis/references/gate-taxonomy.md
A  skills/authoring/feipi-quality-gate-diagnosis/references/scope.md
A  skills/authoring/feipi-quality-gate-diagnosis/templates/handoff.md
A  skills/authoring/feipi-quality-gate-diagnosis/templates/report.md
A  skills/authoring/feipi-session-detail-ui-dev/SKILL.md
A  skills/authoring/feipi-session-detail-ui-dev/references/scope.md
A  skills/authoring/feipi-session-detail-ui-dev/references/ui-boundaries.md
A  skills/authoring/feipi-session-detail-ui-dev/references/visual-gates.md
A  skills/authoring/feipi-session-detail-ui-dev/templates/handoff.md
A  skills/authoring/feipi-session-detail-ui-dev/templates/report.md
A  skills/authoring/feipi-session-ingestion-dev/SKILL.md
A  skills/authoring/feipi-session-ingestion-dev/references/architecture.md
A  skills/authoring/feipi-session-ingestion-dev/references/glossary.md
A  skills/authoring/feipi-session-ingestion-dev/references/patterns.md
A  skills/authoring/feipi-session-ingestion-dev/templates/handoff.md
A  skills/authoring/feipi-session-ingestion-dev/templates/report.md
```

## 2. Required command results

No required command failed. The `./gradlew projects` command completed with `BUILD SUCCESSFUL`; its output contained one internal Gradle task marked `SKIPPED`, which is recorded here and is not counted as a skipped validation command.

| Command | Result | Evidence |
| --- | --- | --- |
| `git branch --show-current` | PASS | exit 0; stdout `main_java` |
| `git status --short` | PASS | exit 0; dirty output present |
| `./gradlew projects` | PASS | exit 0; BUILD SUCCESSFUL; Gradle output includes one internal SKIPPED task (`:build-logic:checkKotlinGradlePluginConfigurationErrors`). |
| `find java -maxdepth 3 -name build.gradle.kts -print \| sort` | PASS | exit 0; 14 build.gradle.kts files listed |
| `rg "project\(" settings.gradle.kts java -g 'build.gradle.kts'` | PASS | exit 0; 53 project dependency lines found |
| `rg "com\.feipi\.session\.browser\.index\.sqlite\|com\.feipi\.session\.browser\.index\.store\.sqlite\|java\.sql" java/application java/web java/scan-engine \|\| true` | PASS | exit 0; production leak file counts application=14, web=21, scan-engine=5; test match counts application=6, web=15, scan-engine=7 |
| `rg "com\.feipi\.session\.browser\.source\.(claude\|codex\|qoder\|json)" java/scan-engine java/application java/web \|\| true` | PASS | exit 0; no output/matches |
| `rg "artifact-normalized\|index-sqlite\|sources" settings.gradle.kts java -g 'build.gradle.kts'` | PASS | exit 0; 17 settings/build-file lines found |

## 3. Current included modules from `settings.gradle.kts`

- `:app-cli`
- `:java:common`
- `:java:app-cli`
- `:java:core-domain`
- `:java:source-spi`
- `:java:sources`
- `:java:artifact-normalized`
- `:java:normalization-engine`
- `:java:index-sqlite`
- `:java:scan-engine`
- `:java:tests:support`
- `:java:tests:architecture`
- `:java:tests:contracts`
- `:java:application`
- `:java:web`

`./gradlew projects` also reports the implicit grouping project `:java` plus the included build `:build-logic`.

## 4. Production dependency baseline

Test dependencies are excluded from this table. Dependency notation is copied from each module's `dependencies {}` block.

| Module | Build file | Production dependencies |
| --- | --- | --- |
| `:java:application` | `java/application/build.gradle.kts` | `implementation(project(":java:common"))`<br>`implementation(project(":java:index-sqlite"))`<br>`implementation(project(":java:core-domain"))`<br>`implementation(libs.slf4j.api)` |
| `:java:web` | `java/web/build.gradle.kts` | `implementation(project(":java:common"))`<br>`implementation(project(":java:application"))`<br>`implementation(project(":java:core-domain"))`<br>`implementation(project(":java:index-sqlite"))`<br>`implementation(libs.slf4j.api)`<br>`implementation(libs.bundles.web)`<br>`implementation(libs.bundles.jackson)` |
| `:java:scan-engine` | `java/scan-engine/build.gradle.kts` | `implementation(project(":java:core-domain"))`<br>`implementation(project(":java:source-spi"))`<br>`implementation(project(":java:sources"))`<br>`implementation(project(":java:normalization-engine"))`<br>`implementation(project(":java:artifact-normalized"))`<br>`implementation(project(":java:index-sqlite"))`<br>`implementation(libs.slf4j.api)` |
| `:java:sources` | `java/sources/build.gradle.kts` | `api(project(":java:source-spi"))`<br>`implementation(libs.bundles.jackson)`<br>`implementation(libs.sqlite.jdbc)` |
| `:java:source-spi` | `java/source-spi/build.gradle.kts` | `api(project(":java:core-domain"))`<br>`implementation(project(":java:common"))` |
| `:java:artifact-normalized` | `java/artifact-normalized/build.gradle.kts` | `api(project(":java:core-domain"))`<br>`implementation(project(":java:common"))`<br>`implementation(libs.bundles.jackson)` |
| `:java:index-sqlite` | `java/index-sqlite/build.gradle.kts` | `implementation(libs.sqlite.jdbc)`<br>`implementation(libs.slf4j.api)`<br>`implementation(libs.bundles.jackson)`<br>`implementation(project(":java:common"))`<br>`implementation(project(":java:core-domain"))` |

Problematic production dependency edges observed against the target architecture:

- `:java:application -> :java:index-sqlite` in `java/application/build.gradle.kts`.
- `:java:web -> :java:index-sqlite` in `java/web/build.gradle.kts`.
- `:java:scan-engine -> :java:sources` in `java/scan-engine/build.gradle.kts`.
- `:java:scan-engine -> :java:artifact-normalized` in `java/scan-engine/build.gradle.kts`.
- `:java:scan-engine -> :java:index-sqlite` in `java/scan-engine/build.gradle.kts`.
- `:java:artifact-normalized` is included by `settings.gradle.kts` and depended on by `java/app-cli/build.gradle.kts`, `java/scan-engine/build.gradle.kts`, and `java/tests/contracts/build.gradle.kts`.

## 5. Production imports of JDBC / concrete SQLite packages

Search scope: `java/application/src/main`, `java/web/src/main`, `java/scan-engine/src/main`.

| Module | File | Matched namespace(s) |
| --- | --- | --- |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/DashboardUseCase.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/DiagnosticsUseCase.java` | `index.sqlite` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/ProjectListUseCase.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/QueryCompositionRoot.java` | `index.sqlite` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/SessionDetailUseCase.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/SessionListUseCase.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/diagnostics/AnomalyDetector.java` | `index.sqlite` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/AggregateQueryRepository.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/SessionQueryRepository.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/SessionResultSetMapper.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/SqlUtils.java` | `java.sql` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/sessiondetail/SessionDetail.java` | `index.sqlite` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/sessiondetail/SessionDetailAssembler.java` | `index.sqlite` |
| `java/application` | `java/application/src/main/java/com/feipi/session/browser/application/sessiondetail/SessionDetailRepository.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/WebCompositionRoot.java` | `java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/ApiSessionDetails.java` | `java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/ApiSessionSummaries.java` | `index.sqlite` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/DashboardApiHandler.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/ExportApiHandler.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/ProjectDetailApiHandler.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/ProjectsApiHandler.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/RoundIndexProjection.java` | `index.sqlite` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/SessionApiHandler.java` | `java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/SessionApiService.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/SessionDetailApiHandler.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/SessionDetailParityAnalyzer.java` | `index.sqlite` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/api/SessionsApiHandler.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/export/ExportHandler.java` | `java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/model/SessionDetailRequest.java` | `java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/model/SessionDetailViewModels.java` | `index.sqlite` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/model/TokenTrendBuckets.java` | `index.sqlite` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/page/DashboardPage.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/page/ProjectsPage.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/page/SessionDetailPage.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/main/java/com/feipi/session/browser/web/page/SessionsPage.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/FingerprintRepository.java` | `java.sql` |
| `java/scan-engine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/FullScanEngine.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/IncrementalScanEngine.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/ScanIndexMaintenance.java` | `java.sql` |
| `java/scan-engine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/ScanLogManager.java` | `java.sql` |

`com.feipi.session.browser.index.store.sqlite` matches in these three production modules: none. Current concrete imports use the older `com.feipi.session.browser.index.sqlite` package.

## 6. Test imports observed by the required all-directory search

The task's required `rg` command searches entire module directories, so test matches are recorded separately from the production leak baseline.

| Module | File | Matched namespace(s) |
| --- | --- | --- |
| `java/application` | `java/application/src/test/java/com/feipi/session/browser/application/UseCaseIntegrationTest.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/test/java/com/feipi/session/browser/application/diagnostics/AnomalyDetectorTest.java` | `index.sqlite` |
| `java/application` | `java/application/src/test/java/com/feipi/session/browser/application/query/repository/AggregateQueryRepositoryTest.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/test/java/com/feipi/session/browser/application/query/repository/SessionQueryRepositoryTest.java` | `index.sqlite, java.sql` |
| `java/application` | `java/application/src/test/java/com/feipi/session/browser/application/sessiondetail/SessionDetailAssemblerTest.java` | `index.sqlite` |
| `java/application` | `java/application/src/test/java/com/feipi/session/browser/application/sessiondetail/SessionDetailRepositoryTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/SecurityHeadersTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/WebCompositionRootTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/ApiContractFixture.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/DashboardResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/ExportResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/GlossaryResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/ProjectDetailResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/ProjectsResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/SessionApiHandlerTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/SessionDetailParityAnalyzerTest.java` | `index.sqlite` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/SessionDetailResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/SessionsResourceApiTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/api/StatePagesContractTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/export/ExportHandlerTest.java` | `index.sqlite, java.sql` |
| `java/web` | `java/web/src/test/java/com/feipi/session/browser/web/page/SessionDetailPageTest.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/FullScanEngineTest.java` | `java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/IncrementalScanEngineCancelTest.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/IncrementalScanEngineTest.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanConcurrencySafetyTest.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanDbFaultTest.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanLogManagerTest.java` | `index.sqlite, java.sql` |
| `java/scan-engine` | `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanPerformanceBaselineTest.java` | `index.sqlite, java.sql` |

## 7. Built-in source provider package imports from `scan-engine`

Search scope: `java/scan-engine/src/main` for `com.feipi.session.browser.source.(claude|codex|qoder|json)`.

- None found. The required all-directory search across `java/scan-engine`, `java/application`, and `java/web` also produced no output.

Module-level issue remains: `java/scan-engine/build.gradle.kts` has `implementation(project(":java:sources"))`, so `scan-engine` still depends on built-in provider implementations even without direct provider-package imports.

## 8. Class locations and likely roles

| Class | Current location | Likely role / boundary observation |
| --- | --- | --- |
| `QueryCompositionRoot` | `java/application/src/main/java/com/feipi/session/browser/application/QueryCompositionRoot.java:16` | Application query composition root; constructs SessionQueryRepository, AggregateQueryRepository, SessionDetailRepository and use cases. Currently exposes/accepts IndexConnection and SchemaVersion from index-sqlite. |
| `WebCompositionRoot` | `java/web/src/main/java/com/feipi/session/browser/web/WebCompositionRoot.java:56` | Web/Javalin composition root; creates Javalin, templates, page/API handlers, routes and exception handlers. Currently catches java.sql.SQLException directly. |
| `FullScanEngine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/FullScanEngine.java:65` | Full scan pipeline; checks schema, scans source adapters, normalizes candidates, writes normalized artifacts, maps artifacts to index rows, and batches SQLite writes. |
| `IncrementalScanEngine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/IncrementalScanEngine.java:52` | Incremental scan pipeline; loads indexed fingerprints, classifies candidate state, reuses full-scan processing for changed candidates, and writes scan metadata/index updates. |
| `NormalizedArtifactWriter` | `java/artifact-normalized/src/main/java/com/feipi/session/browser/artifact/normalized/NormalizedArtifactWriter.java:55` | Fail-safe normalized artifact file writer; serializes NormalizedSessionArtifact to deterministic JSON plus metadata using temp-file and atomic move semantics. |
| `CanonicalJsonWriter` | `java/artifact-normalized/src/main/java/com/feipi/session/browser/artifact/normalized/CanonicalJsonWriter.java:43` | Deterministic JSON serializer used by NormalizedArtifactWriter; configures Jackson ordering, duplicate detection and domain serializers. |
| `NormalizedArtifactLoader` | `java/index-sqlite/src/main/java/com/feipi/session/browser/index/sqlite/NormalizedArtifactLoader.java:41` | Disk loader/deserializer for normalized artifact JSON; validates into NormalizedSessionArtifact. Located in concrete index-sqlite and imported by application/web. |
| `SessionQueryRepository` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/SessionQueryRepository.java:44` | Application-layer JDBC read repository for session list/search/count/lookup queries over IndexConnection and SessionRow DTOs. |
| `AggregateQueryRepository` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/AggregateQueryRepository.java:49` | Application-layer JDBC read repository for project, dashboard, trend, token/tool/model aggregate queries over IndexConnection and row DTOs. |
| `SessionResultSetMapper` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/SessionResultSetMapper.java:20` | Package-private mapper from JDBC ResultSet to index-sqlite SessionRow, with explicit sessions table column list. |
| `SqlUtils` | `java/application/src/main/java/com/feipi/session/browser/application/query/repository/SqlUtils.java:12` | Package-private SQL helper for null-to-empty conversion, PreparedStatement binding and WHERE-clause parameter holder. |

## 9. Short risk list for later tasks

- Extracting `:java:index-api` will need clear ownership of row/query DTOs currently in `com.feipi.session.browser.index.sqlite` and widely imported by `application` and `web`.
- `application` currently contains concrete JDBC repositories (`SessionQueryRepository`, `AggregateQueryRepository`, `SessionDetailRepository`) and `java.sql` helpers, so decoupling it may require moving implementations to the concrete store module while preserving use-case APIs.
- `web` currently handles `java.sql.SQLException` and imports SQLite row types in pages, API handlers, models, and export paths; changing DTO boundaries can affect many route/template callers.
- `scan-engine` couples scan logic to JDBC/SQLite (`Connection`, `IndexSchema`, `WriteBatch`, row mappers), `:java:sources`, and `:java:artifact-normalized`; split the refactor into source-adapter injection, index write-port extraction, and artifact-writer relocation.
- Removing `:java:artifact-normalized` impacts `java/app-cli/build.gradle.kts`, `java/scan-engine/build.gradle.kts`, `java/tests/contracts/build.gradle.kts`, and classes under `java/artifact-normalized/src/main/java/com/feipi/session/browser/artifact/normalized/`.
- `NormalizedArtifactLoader` lives in concrete `:java:index-sqlite` but is imported by `application` and `web`; decide whether artifact loading becomes an index API port, application service, or internal concrete-store helper.
- Tests in `application`, `web`, and `scan-engine` intentionally reference concrete SQLite for fixtures; final architecture rules allow tests to reference adapters, but production-vs-test enforcement must be explicit.
- Worktree was already dirty before this report; subsequent refactor tasks should avoid mixing unrelated agent/harness/skill changes with Java architecture edits.

## 10. Blockers

- None for Task 01. Current branch is `main_java`; task prompt matches the repository's current baseline modules and dependencies.
