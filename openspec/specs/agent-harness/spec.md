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

#### Scenario: Fixture server cannot start

- **Given** a browser quality gate requires the HIFI fixture session
- **And** the default `BASE_URL` is not serving that fixture session
- **When** the temporary fixture server cannot start
- **Then** the fixture-dependent browser gate SHALL return `BLOCKED`
- **And** it SHALL NOT continue into a long Playwright timeout

### Requirement: Test trigger mapping and skip semantics

The harness SHALL distinguish tests that are not triggered by path-to-target mapping from tests that are triggered but skipped at runtime.
Any selected test or required gate SHALL treat skipped outcomes as failed or blocked validation, and full or release regression SHALL prove zero skipped tests.

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
