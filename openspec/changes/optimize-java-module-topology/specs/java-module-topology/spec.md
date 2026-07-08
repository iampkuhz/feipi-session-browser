# Spec: Java module topology

## Requirement: Java production modules shall expose coarse-grained architecture boundaries

Java production module topology must avoid one-provider-per-module fragmentation when package boundaries provide sufficient isolation.

### Scenario: Source implementations are grouped behind Source SPI

- **Given** source adapter implementations for JSON parsing, Claude, Codex and Qoder
- **When** Gradle evaluates Java production modules
- **Then** those implementations are provided by `:java:sources`
- **And** `:java:source-spi` remains the stable provider-neutral interface module

## Requirement: Query contracts shall live with application query use cases

Query DTO/filter/sort/anomaly contracts must be provided by the application layer when they are only used by application/web query flows.

### Scenario: Query API module is merged

- **Given** code imports `com.feipi.session.browser.query.api` types
- **When** the project compiles
- **Then** those types are supplied by `:java:application`
- **And** there is no standalone `:java:query-api` Gradle module

## Requirement: Transitional module dependencies shall be eliminated

Architecture boundary configuration must not rely on transition dependencies after this change.

### Scenario: Module boundary check runs in strict mode

- **Given** the repository module boundary configuration
- **When** `python3 scripts/quality/check_java_module_boundaries.py --fail-transition` is executed
- **Then** the command succeeds with zero transition dependency findings

## Requirement: Test-only modules shall be grouped under a tests namespace

Test support, architecture guard tests and cross-module contract tests must be grouped under a common Gradle namespace without merging their distinct build roles.

### Scenario: Test modules are nested but remain separate

- **Given** the repository has test support utilities, architecture tests and contract tests
- **When** Gradle evaluates Java subprojects
- **Then** test support utilities are provided by `:java:tests:support`
- **And** architecture guard tests are provided by `:java:tests:architecture`
- **And** cross-module contract tests are provided by `:java:tests:contracts`
- **And** there are no standalone `:java:test-support`, `:java:architecture-tests` or `:java:contract-tests` Gradle modules
