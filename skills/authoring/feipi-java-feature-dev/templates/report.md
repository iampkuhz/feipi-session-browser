## Summary

<一句话描述本次变更>

## Changed files

- `java/<module>/src/main/java/...`
- `java/<module>/src/test/java/...`
- ...

## Decisions

- <关键设计决策及其理由>

## Gates

| Gate | Result |
|---|---|
| `./scripts/session-browser.sh test` | <PASS/BLOCKED/FAIL/NOT_RUN> |
| `./java/gradlew -p java check` | <PASS/BLOCKED/FAIL/NOT_RUN> |
| `python3 scripts/gates/cli.py run --mode incremental` | <PASS/BLOCKED/FAIL/NOT_RUN> |

`BLOCKED` 表示检查完成并确认仓库有阻断问题；`FAIL` 表示 Gate 未能完成、无法判断仓库；未运行统一写
`NOT_RUN`，且不得描述为 `PASS`。

## Risks

- <风险或 none>

## Follow-up

- <后续事项或 none>
