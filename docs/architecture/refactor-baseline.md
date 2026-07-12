# Java architecture refactor baseline

Audit date: 2026-07-09  
Task: `.qoder/task-packs/feipi-java-architecture/tasks/01_baseline_architecture_audit.md`

## 1. Branch and dirty status

- Current branch from `git branch --show-current`: `main_java`
- Dirty status before creating this report from `git status --short`: no output; working tree was clean.
- Expected change after this task: `docs/architecture/refactor-baseline.md` only.

## 2. Included modules from `settings.gradle.kts`

`settings.gradle.kts` currently includes:

- `:app-cli`
- `:java:common`
- `:java:app-cli`
- `:java:core-domain`
- `:java:source-spi`
- `:java:sources`
- `:java:normalization-engine`
- `:java:index-api`
- `:java:index-store-sqlite`
- `:java:scan-engine`
- `:java:tests:support`
- `:java:tests:architecture`
- `:java:tests:contracts`
- `:java:application`
- `:java:web`

Observed drift from older task-pack context: `:java:index-api` and `:java:index-store-sqlite` already exist; `:java:artifact-normalized` and `:java:index-sqlite` are not included.

## 3. Production dependency table

Production dependencies are taken from each module's `build.gradle.kts`, excluding `testImplementation` and `testRuntimeOnly`.

| Module | Build file | Current production dependencies |
| --- | --- | --- |
| `:java:application` | `java/application/build.gradle.kts` | `api(project(":java:index-api"))`; `implementation(project(":java:common"))`; `implementation(project(":java:core-domain"))`; `implementation(libs.slf4j.api)` |
| `:java:web` | `java/web/build.gradle.kts` | `implementation(project(":java:common"))`; `implementation(project(":java:application"))`; `implementation(project(":java:core-domain"))`; `implementation(libs.slf4j.api)`; `implementation(libs.bundles.web)`; `implementation(libs.bundles.jackson)` |
| `:java:scan-engine` | `java/scan-engine/build.gradle.kts` | `implementation(project(":java:common"))`; `implementation(project(":java:core-domain"))`; `implementation(project(":java:source-spi"))`; `implementation(project(":java:normalization-engine"))`; `implementation(project(":java:index-api"))`; `implementation(libs.bundles.jackson)`; `implementation(libs.slf4j.api)` |
| `:java:sources` | `java/sources/build.gradle.kts` | `api(project(":java:source-spi"))`; `implementation(libs.bundles.jackson)`; `implementation(libs.sqlite.jdbc)` |
| `:java:source-spi` | `java/source-spi/build.gradle.kts` | `api(project(":java:core-domain"))`; `implementation(project(":java:common"))` |
| `:java:artifact-normalized` | not present | Module is not included in `settings.gradle.kts`; no `java/artifact-normalized/build.gradle.kts` was found by the required `find` command. |
| `:java:index-sqlite` | not present | Module is not included in `settings.gradle.kts`; current concrete store module is `:java:index-store-sqlite`. |
| `:java:index-store-sqlite` | `java/index-store-sqlite/build.gradle.kts` | `implementation(libs.sqlite.jdbc)`; `implementation(libs.slf4j.api)`; `implementation(libs.bundles.jackson)`; `implementation(project(":java:common"))`; `implementation(project(":java:core-domain"))`; `api(project(":java:index-api"))` |
| `:java:index-api` | `java/index-api/build.gradle.kts` | `api(project(":java:core-domain"))`; `implementation(project(":java:common"))` |

## 4. SQLite/JDBC imports in `application`, `web`, and `scan-engine`

Required broad command scanned `java/application`, `java/web`, and `java/scan-engine`.

### Production source (`src/main`)

No files under these production paths import `java.sql.*`, `com.feipi.session.browser.index.sqlite.*`, or `com.feipi.session.browser.index.store.sqlite.*`:

- `java/application/src/main`
- `java/web/src/main`
- `java/scan-engine/src/main`

### Non-production test files matched by the broad required command

The following test files import `java.sql.*` and/or `com.feipi.session.browser.index.store.sqlite.*`:

- `java/application/src/test/java/com/feipi/session/browser/application/diagnostics/AnomalyDetectorTest.java`
- `java/application/src/test/java/com/feipi/session/browser/application/query/repository/AggregateQueryRepositoryTest.java`
- `java/application/src/test/java/com/feipi/session/browser/application/query/repository/SessionQueryRepositoryTest.java`
- `java/application/src/test/java/com/feipi/session/browser/application/sessiondetail/SessionDetailAssemblerTest.java`
- `java/application/src/test/java/com/feipi/session/browser/application/sessiondetail/SessionDetailRepositoryTest.java`
- `java/application/src/test/java/com/feipi/session/browser/application/UseCaseIntegrationTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/FullScanEngineTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/IncrementalScanEngineCancelTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/IncrementalScanEngineTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanConcurrencySafetyTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanDbFaultTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanLogManagerTest.java`
- `java/scan-engine/src/test/java/com/feipi/session/browser/scan/engine/ScanPerformanceBaselineTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/ApiContractFixture.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/DashboardResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/ExportResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/GlossaryResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/ProjectDetailResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/ProjectsResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/SessionApiHandlerTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/SessionDetailParityAnalyzerTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/SessionDetailResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/SessionsResourceApiTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/api/StatePagesContractTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/export/ExportHandlerTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/page/SessionDetailPageTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/SecurityHeadersTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/WebCompositionRootTest.java`
- `java/web/src/test/java/com/feipi/session/browser/web/WebTestComposition.java`

## 5. Built-in source-provider imports in `scan-engine`

No files under `java/scan-engine` import these built-in provider implementation packages:

- `com.feipi.session.browser.source.claude.*`
- `com.feipi.session.browser.source.codex.*`
- `com.feipi.session.browser.source.qoder.*`
- `com.feipi.session.browser.source.json.*`

## 6. Current class locations and likely roles

| Requested class | Current location | Likely role |
| --- | --- | --- |
| `QueryCompositionRoot` | `java/application/src/main/java/com/feipi/session/browser/application/QueryCompositionRoot.java` | Application composition root; wires query use cases from abstract `SessionQueryPort`, `AggregateQueryPort`, `SessionDetailPort`, `NormalizedArtifactReader`, optional `QueryCache`, and schema version. |
| `WebCompositionRoot` | `java/web/src/main/java/com/feipi/session/browser/web/WebCompositionRoot.java` | Web composition root; creates/configures Javalin, Pebble templates, security headers, routes, API/page handlers, and exception handlers around `QueryCompositionRoot`. |
| `FullScanEngine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/FullScanEngine.java` | Full scan pipeline; receives `IndexWriterPort` and `ScanConfig`, uses `SourceAdapter`, `NormalizationEngine`, and `NormalizedArtifactWriter` to discover, normalize, write artifacts, and update the index through ports. |
| `IncrementalScanEngine` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/IncrementalScanEngine.java` | Incremental scan pipeline; compares candidate fingerprints, handles scan-logic versioning/cancellation/progress, and writes changed sessions through `IndexWriterPort`. |
| `NormalizedArtifactWriter` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/artifact/NormalizedArtifactWriter.java` | Failure-safe normalized artifact writer; serializes `NormalizedSessionArtifact`, writes data/meta files via temp-file plus atomic move, and enforces artifact path safety. |
| `CanonicalJsonWriter` | `java/scan-engine/src/main/java/com/feipi/session/browser/scan/artifact/CanonicalJsonWriter.java` | Deterministic JSON serializer for normalized artifacts; configures Jackson for stable map ordering, compact UTF-8 output, enum value output, and duplicate detection. |
| `NormalizedArtifactLoader` | `java/index-store-sqlite/src/main/java/com/feipi/session/browser/index/store/sqlite/loader/NormalizedArtifactLoader.java` | Concrete-store artifact loader; reads normalized JSON artifacts from disk and reconstructs validated `NormalizedSessionArtifact` instances for SQLite-backed details. |
| `SessionQueryRepository` | exact class name not present; current implementation is `java/index-store-sqlite/src/main/java/com/feipi/session/browser/index/store/sqlite/repository/SqliteSessionQueryRepository.java` | SQLite read repository implementing `SessionQueryPort`; performs session list/search/count/lookup SQL with parameter binding and maps rows through `SqliteSessionResultSetMapper`. |
| `AggregateQueryRepository` | exact class name not present; current implementation is `java/index-store-sqlite/src/main/java/com/feipi/session/browser/index/store/sqlite/repository/SqliteAggregateQueryRepository.java` | SQLite aggregate repository implementing `AggregateQueryPort`; provides project/dashboard/trend/token/tool/model aggregate queries. |
| `SessionResultSetMapper` | exact class name not present; current implementation is `java/index-store-sqlite/src/main/java/com/feipi/session/browser/index/store/sqlite/mapper/SqliteSessionResultSetMapper.java` | JDBC `ResultSet` to `SessionRow` mapper; centralizes explicit session columns and null-to-empty conversions. |
| `SqlUtils` | exact class name not present; current implementation is `java/index-store-sqlite/src/main/java/com/feipi/session/browser/index/store/sqlite/util/SqliteSqlUtils.java` | SQLite repository utility holder; currently provides `nullToEmpty`, prepared-statement parameter binding, and immutable `WhereClauses`. |

## 7. Required commands run

All required commands were run from repository root.

| Command | Result |
| --- | --- |
| `git branch --show-current` | Exit 0; output `main_java`. |
| `git status --short` | Exit 0; no output before this report was created. |
| `./gradlew projects` | Exit 0; Gradle reported `BUILD SUCCESSFUL` and listed modules shown above. |
| `find java -maxdepth 3 -name build.gradle.kts -print \| sort` | Exit 0; found build files under `java/app-cli`, `java/application`, `java/common`, `java/core-domain`, `java/index-api`, `java/index-store-sqlite`, `java/normalization-engine`, `java/scan-engine`, `java/source-spi`, `java/sources`, `java/tests/architecture`, `java/tests/contracts`, `java/tests/support`, and `java/web`. |
| `rg "project\(" settings.gradle.kts java -g 'build.gradle.kts'` | Exit 0; project dependency lines matched and are summarized in the dependency table. |
| `rg "com\.feipi\.session\.browser\.index\.sqlite\|com\.feipi\.session\.browser\.index\.store\.sqlite\|java\.sql" java/application java/web java/scan-engine \|\| true` | Exit 0 due to `\|\| true`; broad matches were limited to test files listed in section 4. No production `src/main` matches were found in follow-up import-specific check. |
| `rg "com\.feipi\.session\.browser\.source\.(claude\|codex\|qoder\|json)" java/scan-engine java/application java/web \|\| true` | Exit 0 due to `\|\| true`; no output. |
| `rg "artifact-normalized\|index-sqlite\|sources" settings.gradle.kts java -g 'build.gradle.kts'` | Exit 0; output only `settings.gradle.kts:    "java:sources",`, `java/tests/contracts/build.gradle.kts:    testImplementation(project(":java:sources"))`, `java/app-cli/build.gradle.kts:    implementation(project(":java:sources"))`, and unrelated `java/app-cli/build.gradle.kts` `resources` lines. |

No required command failed.

## 8. Additional validation command

Because the task pack constraints require architecture tests not be skipped, this audit also ran:

| Command | Result |
| --- | --- |
| `./gradlew :java:tests:architecture:test` | Exit 0; `BUILD SUCCESSFUL`; task was `UP-TO-DATE`. |

## 9. Risks and recommended next-step notes

- The task-pack context still describes older modules (`:java:artifact-normalized`, `:java:index-sqlite`) as current, but the repository already has `:java:index-api` and `:java:index-store-sqlite`, and no included `:java:artifact-normalized`. Later task prompts should be checked against this actual state before editing.
- `application`, `web`, and `scan-engine` production code currently have no direct SQLite/JDBC imports, but many tests still import SQLite/JDBC. Future automated `rg` gates should scope to `src/main` unless tests are intentionally being migrated to abstract fixtures.
- `:java:application` and `:java:web` still have test-only dependencies on `:java:index-store-sqlite`; production dependency checks must distinguish production configurations from test configurations.
- `:java:sources` has a production `libs.sqlite.jdbc` dependency. This matches the target note that providers may use SQLite JDBC if needed, but `:java:source-spi` must remain free of Jackson/SQLite.
- Searches over `java/**` can accidentally include generated Gradle/Spotless output under `java/**/build`; future static checks should exclude `**/build/**`.
- Composition of concrete store classes appears centralized outside `application`/`web` production code, but future changes should keep concrete `index.store.sqlite` references confined to `java/app-cli`, tests, and `java/index-store-sqlite`.

## 10. Final verification after writing this report

| Command | Result |
| --- | --- |
| `test -f docs/architecture/refactor-baseline.md && printf 'report exists\n'` | Exit 0; output `report exists`. |
| `git status --short` | Exit 0; output only ` M docs/architecture/refactor-baseline.md`. |
| `git diff --name-only -- settings.gradle.kts java app-cli build.gradle.kts gradle.properties gradle .qoder openspec \|\| true` | Exit 0; no output, confirming no production Java, build, `.qoder`, or `openspec` files were changed. |
| `git diff --name-only` | Exit 0; output only `docs/architecture/refactor-baseline.md`. |
| 历史 Gate runner 观测 | 该双轨入口已下线；当前统一入口为 `python3 scripts/gates/cli.py`。 |

The direct quality-gate script invocation is documented as a permission-mode issue; the Python interpreter fallback completed successfully. No forbidden source/build files were modified.
