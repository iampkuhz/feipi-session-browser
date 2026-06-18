# Spec: No test skips

## Requirement: Selected tests cannot skip

Any test selected by path mapping, explicit command, full regression, or release regression must run to pass/fail/error and must not report skipped outcomes.

### Scenario: Full pytest suite runs

- **Given** the repository test script runs without path arguments
- **When** `./scripts/session-browser.sh test` completes successfully
- **Then** pytest reports zero skipped tests
- **And** any skipped pytest outcome changes the run to failed validation

### Scenario: Direct Playwright suite runs

- **Given** Playwright tests are run from the repository root
- **When** `npx playwright test` completes
- **Then** Playwright reports zero skipped tests
- **And** any skipped Playwright test changes the run to failed validation

## Requirement: Static skip APIs are forbidden in tests

The quality system must reject new test skip APIs before runtime.

### Scenario: Python test contains skip API

- **Given** a Python file under `tests/` contains `pytest.skip`, `pytest.mark.skip`, or `pytest.mark.skipif`
- **When** the no-skip quality gate runs
- **Then** the gate fails with the file and line number

### Scenario: Playwright test contains skip API

- **Given** a Playwright test contains `test.skip`, `test.describe.skip`, or `test.fixme`
- **When** the no-skip quality gate runs
- **Then** the gate fails with the file and line number

## Requirement: Not triggered remains distinct from skipped

Changed-files mapping may leave unrelated gates not triggered, but selected gates cannot contain skipped outcomes.

### Scenario: Gate not selected by changed files

- **Given** changed files do not match a gate pattern
- **When** required quality targets are computed
- **Then** that gate remains not triggered
- **And** reports do not call it skipped

### Scenario: Release regression includes a test

- **Given** a full or release regression includes a test or gate
- **When** fixture data or environment is missing
- **Then** validation fails or blocks
- **And** it must not pass by skipping the test
