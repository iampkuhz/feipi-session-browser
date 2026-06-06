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
