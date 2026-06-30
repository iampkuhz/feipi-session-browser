# Spec: Agent Harness

## Requirement: Python standard manual tooling baseline

The repository SHALL keep `python-standard` as a manual Python tooling quality baseline aligned with the Java-product repository shape.

### Scenario: Product Python source has been retired

- **Given** the repository no longer contains `src/session_browser` product Python modules
- **When** `python-standard` runs Python type, coverage, lint, dead-code, or dependency checks
- **Then** those checks SHALL NOT require the retired package path to exist
- **And** they SHALL focus on Python tooling under `scripts/` and related tooling tests.

### Scenario: Legacy UI tests are not part of Python tooling coverage

- **Given** historical UI/Jinja tests require product Python runtime dependencies that are no longer part of the product
- **When** `python-standard` runs coverage
- **Then** coverage SHALL execute the Python tooling test subset instead of the full product/UI pytest suite
- **And** the gate SHALL NOT add old product dependencies solely for those historical tests.

### Scenario: Historical complexity debt is reported without blocking the manual baseline

- **Given** existing Python tooling scripts contain historical complexity above the current Xenon threshold
- **When** `python-standard` runs the complexity step
- **Then** the step SHALL print the complexity report for operator visibility
- **And** it SHALL NOT fail the `python-standard` target until a separate ratchet change defines blocking thresholds.

### Scenario: Vulnerability service network failure is diagnostic for the manual baseline

- **Given** the Python tooling dependency lock can be read locally
- **And** the vulnerability service is unavailable because of network, proxy, or certificate failures
- **When** `python-standard` runs the audit step
- **Then** it SHALL report the vulnerability-service connectivity problem as a non-blocking diagnostic
- **And** it SHALL continue to run local Bandit high-severity checks as the blocking audit guard.
