# Spec: Session Detail Normalization Quality Contracts

## Requirement: Structured normalized artifact

Normalized artifact output MUST expose stable snake_case JSON for session, source files, calls, tools, diagnostics, source unit catalog, and source unit sequences while the Java pipeline keeps typed domain objects internally.

### Scenario: Canonical artifact uses normalized v3 field names

- **Given** the Java normalization pipeline serializes a normalized session artifact
- **When** the canonical JSON writer emits bytes
- **Then** the root SHALL include `schema_version`, `agent`, `source`, `session`, `calls`, `tool_executions`, and `diagnostics`
- **And** non-empty source unit data SHALL use `source_unit_catalog` and `source_unit_sequences`
- **And** optional empty parent fields SHALL serialize as empty strings rather than ambiguous nested Optional objects.

## Requirement: Codex child rollout attribution

Codex child rollout files MUST be materialized as subagent calls only when stable parent evidence is visible.

### Scenario: Child rollout has explicit parent evidence

- **Given** a top-level Codex rollout spawns a child thread via `spawn_agent`
- **And** the child rollout session metadata exposes the same parent thread id
- **When** the source adapter parses the parent candidate
- **Then** child LLM calls and child tool executions SHALL use `scope = subagent`
- **And** each child call SHALL expose `subagent_id`, `parent_tool_call_id`, and a parent call id derived from the parent `spawn_agent` call.

## Requirement: Session samples are blocking regression tests

Session sample integration tests MUST fail the build on schema drift or missing sample inputs.

### Scenario: Sample drift occurs

- **Given** a sample has `expected.normalized.jsonc`
- **When** the Java production pipeline output differs structurally
- **Then** `sampleIntegrationTest` SHALL fail and write a drift report.

## Requirement: Python and comment quality contracts

Repository quality gates MUST enforce Python runtime compatibility, warning-free output, and Chinese-first comments for covered scripts and frontend assets.

### Scenario: Runtime or comments drift

- **Given** Python or script/frontend quality surfaces change
- **When** doctor or script comment language gates run
- **Then** they SHALL reject unsupported Python versions, dependency lock drift, warning output, and non-Chinese explanatory comments.
