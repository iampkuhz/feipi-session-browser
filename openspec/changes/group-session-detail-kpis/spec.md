# Spec: Session Detail KPI Grouping

## Requirement: Grouped KPI Analysis

The session detail hero SHALL separate token analysis metrics from call-count analysis metrics inside `.sd-kpis`.

### Scenario: Token analysis metrics render together

- **Given** a session detail page with token totals
- **When** the hero KPI strip renders
- **Then** Tokens, Fresh, Cache R, Cache W, and Output appear in one grouped KPI section

### Scenario: Call-count metrics render together

- **Given** a session detail page with round, tool, failure, and LLM call counts
- **When** the hero KPI strip renders
- **Then** Rounds, Tools, Failed, and LLM Calls appear in a separate grouped KPI section
