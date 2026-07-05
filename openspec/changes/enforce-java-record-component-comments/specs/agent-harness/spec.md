# Spec: Agent Harness Delta

## Requirement: Java source gates enforce record component documentation

The Java source quality target SHALL include a gate that requires every Java record component in production source to be documented by a Chinese `@param` entry in the record type Javadoc.

### Scenario: Record component lacks a tag

- **Given** a Java file under `java/**/src/main/java/` declares `record ProjectListSummaryRow(long projectCount)`
- **And** the record Javadoc has no `@param projectCount` entry
- **When** the `java-src` quality target or root `check` runs
- **Then** the Java record component Javadoc gate SHALL fail with the file, line, record name, and missing component name.

### Scenario: Record component tag is English-only

- **Given** a record component has an `@param` entry whose description contains only English narrative text
- **When** the Java record component Javadoc gate runs
- **Then** the gate SHALL fail because the component explanation is not Chinese narrative.

### Scenario: Record component tags are Chinese

- **Given** every record component has a matching `@param` entry with Chinese explanation and allowed English identifiers or technical terms
- **When** the Java record component Javadoc gate runs
- **Then** the gate SHALL pass for that record.

## Requirement: Codex Stop routes Java changes fail-closed without session identity

Codex Stop SHALL not silently pass as read-only when Java files are dirty or untracked but hook session identity is unavailable.

### Scenario: Codex Stop has no session id and Java file is untracked

- **Given** `.codex/hooks/stop_check.sh` invokes the shared Stop runner without a session id
- **And** the working tree contains an untracked Java source file
- **When** the shared Stop runner collects changed files
- **Then** it SHALL include the untracked Java file via git dirty/untracked fallback
- **And** required target selection SHALL include `java-src`.
