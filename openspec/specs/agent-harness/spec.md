# Agent Harness Spec

## Requirements

### Requirement: OpenSpec-first workflow

The repository SHALL require an OpenSpec change before non-trivial implementation work.

### Requirement: Acceptance contract mapping gate

The harness SHALL run an acceptance-contract mapping gate whenever acceptance contract docs or tests change.

#### Scenario: Contract docs change

- **Given** a file under `docs/acceptance-contracts/` changes
- **When** stop quality targets are computed
- **Then** `acceptance-contracts` SHALL be required
- **And** `scripts/quality/validate_acceptance_contracts.py` SHALL run

#### Scenario: Test markers change

- **Given** a file under `tests/` changes
- **When** stop quality targets are computed
- **Then** `acceptance-contracts` SHALL be required
- **And** orphan `contract_case` IDs SHALL fail the gate

### Requirement: Shared agent stop entrypoint

Claude Code, Codex, and Qoder stop hooks SHALL delegate to a shared harness runner instead of duplicating quality-gate logic.

#### Scenario: Shell deletion bypasses write hook evidence

- **Given** an agent deletes an acceptance contract file through a shell command
- **When** the stop hook runs
- **Then** the shared runner SHALL inspect `git status --short --untracked-files=all`
- **And** the deleted contract file SHALL still trigger the required quality target

### Requirement: Deterministic quality gate runtime

Quality gates SHALL run with a project dependency-capable Python interpreter instead of assuming PATH `python3` has the required runtime and dev dependencies.

The local harness SHALL use the same Python selection order for `deps`, `test`, doctor, and required quality gates: `SESSION_BROWSER_PYTHON` when executable, then the repository `.venv` interpreter, then the repository-approved fallback Python. Dependency declaration files and the checked-in requirements lock SHALL be treated as part of the runtime contract, and missing or inconsistent lock state SHALL fail or block doctor and required gates instead of producing a passing warning.

#### Scenario: Python gate runs from an agent hook

- **Given** an agent hook invokes the shared quality gate runner from an environment where PATH `python3` lacks project dependencies
- **When** a Python-based quality gate runs
- **Then** the gate runner SHALL prefer an explicit project Python or local project environment
- **And** `pytest` SHALL run through that Python with `-m pytest`

#### Scenario: Local test script runs without a project venv

- **Given** no `.venv` exists in the repository
- **And** PATH `python3` lacks dev dependencies
- **When** `./scripts/session-browser.sh test` runs
- **Then** the script SHALL prefer an explicit project Python or a Python 3 `python` before falling back to PATH `python3`

#### Scenario: Dependency lock is inconsistent

- **Given** runtime or dev dependency declarations differ from the repository-approved requirements lock
- **When** `scripts/harness/doctor.sh` or a required quality gate checks the local environment
- **Then** the check SHALL return non-zero or `BLOCKED`
- **And** the report SHALL identify the dependency declaration and lock mismatch.

#### Scenario: Fixture server cannot start

- **Given** a browser quality gate requires the HIFI fixture session
- **And** the default `BASE_URL` is not serving that fixture session
- **When** the temporary fixture server cannot start
- **Then** the fixture-dependent browser gate SHALL return `BLOCKED`
- **And** it SHALL NOT continue into a long Playwright timeout

### Requirement: Canonical two-part release version

The repository SHALL use a two-part `x.y` version as the canonical maintenance release version for local scripts, help text, and release validation.

#### Scenario: Local script reports v0.4

- **Given** `VERSION` contains `0.4`
- **When** `./scripts/session-browser.sh version` runs
- **Then** the command SHALL print `0.4`
- **And** script help SHALL present `x.y` as the default `set-version` example.

#### Scenario: Release command validates two-part version

- **Given** a release command receives `0.4`
- **When** the command validates the target version
- **Then** `0.4` SHALL be accepted as a valid release version
- **And** malformed versions SHALL fail before build, packaging, or Podman actions begin.

### Requirement: Test trigger mapping and skip semantics

The harness SHALL distinguish tests that are not triggered by path-to-target mapping from tests that are triggered but skipped at runtime.
Any selected test or required gate SHALL treat skipped outcomes as failed or blocked validation, and full or release regression SHALL prove zero skipped tests.
Any selected test, required gate, full regression, or release regression SHALL also treat warning outcomes as failed or blocked validation unless the warning cause is fixed or the trigger is removed.

#### Scenario: Change mapping does not select a gate

- **Given** a changed file does not match any pattern for a gate
- **When** required quality targets and gates are computed
- **Then** that gate SHALL be treated as not triggered
- **And** reports SHALL NOT describe it as a skipped test

#### Scenario: Selected Playwright gate reports skipped tests

- **Given** a Playwright gate is selected by path mapping, explicit command, or full regression
- **When** the Playwright command reports one or more skipped tests
- **Then** the gate SHALL fail or block instead of passing
- **And** the agent SHALL either provide the missing fixture/environment or remove the test from the triggered mapping

#### Scenario: Selected pytest gate reports skipped tests

- **Given** a pytest gate is selected by path mapping, explicit command, required baseline, or full regression
- **When** pytest reports one or more skipped outcomes
- **Then** the gate SHALL fail or block instead of passing
- **And** the report SHALL identify the outcome as skipped after trigger, not not triggered

#### Scenario: Selected pytest gate emits a warning

- **Given** `./scripts/session-browser.sh test` or a pytest quality gate is selected by explicit command, path mapping, required baseline, full regression, or release regression
- **When** pytest emits a warning summary, deprecation warning, fixture warning, or other pytest warning
- **Then** the selected gate SHALL NOT report `PASS`
- **And** the report SHALL identify the outcome as warning after trigger, not not triggered.

#### Scenario: Required doctor emits a warning

- **Given** doctor is part of required validation
- **When** doctor detects a warning condition in the Python environment, dependency lock, local-only files, or quality-gate prerequisites
- **Then** the required validation SHALL fail or block
- **And** it SHALL NOT be summarized as `PASS with warnings`.

#### Scenario: Full regression is requested

- **Given** a release or full regression has been requested
- **When** any included test would skip because required fixture or environment is missing
- **Then** the regression SHALL be reported as `FAIL` or `BLOCKED`
- **And** skipped tests SHALL NOT be counted as passing validation
- **And** the successful regression evidence SHALL show `0 skipped`

#### Scenario: New test skip API is introduced

- **Given** a change adds `pytest.skip`, `pytest.mark.skip`, `pytest.mark.skipif`, Playwright `test.skip()`, `test.describe.skip`, or `test.fixme`
- **When** the `noTestSkips` gate runs `scripts/quality/check_no_test_skips.py`
- **Then** the gate SHALL fail with the file and line number
- **And** the new skip SHALL NOT be accepted as a passing quality gate result

### Requirement: Pytest suite is warning-free for supported fixture patterns

The test suite SHALL avoid pytest fixture patterns that emit class-scoped fixture warnings under the supported pytest version and upcoming pytest 10 behavior.

#### Scenario: Session Detail page contract tests run with pytest warnings as errors

- **Given** `tests/session_detail/test_session_detail_page.py` is selected
- **When** it runs with pytest warnings promoted to errors
- **Then** collection and execution SHALL complete without class-scoped fixture warnings
- **And** existing contract-case markers SHALL remain attached to the same behavioral assertions.
