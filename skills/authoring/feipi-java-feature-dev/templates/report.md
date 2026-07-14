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
| `./scripts/session-browser.sh test` | <PASS/FAIL> |
| `./gradlew check` | <PASS/FAIL> |
| `./gradlew :java:tests:quality-gates:runJavaQualityGates -PfeipiJavaQualityRules=java-api-snapshot` | <PASS/FAIL/skipped> |
| `python scripts/gates/cli.py` | <PASS/FAIL/skipped> |

## Risks

- <风险或 none>

## Follow-up

- <后续事项或 none>
