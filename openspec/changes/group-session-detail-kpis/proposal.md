# Proposal: Group Session Detail KPIs

## Problem

Session detail hero KPIs mix token volume and call-count metrics in one flat row. This makes token cache analysis harder to scan.

## Scope

- Group Tokens, Fresh, Cache R, Cache W, and Output together in `.sd-kpis`.
- Group Rounds, Tools, Failed, and LLM Calls separately in `.sd-kpis`.
- Keep the change limited to the session detail hero view model, template, CSS, and session detail UI spec.

## Non-goals

- No changes to token normalization, indexing, trace rows, payload rendering, or data collection.
- No redesign of the broader session detail layout.

## User impact

Users can compare total token usage with token composition directly, while call-count metrics remain visually separate.

## Validation strategy

- Render the session detail template through existing tests.
- Run the session detail quality gate.
