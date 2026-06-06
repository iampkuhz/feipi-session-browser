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
