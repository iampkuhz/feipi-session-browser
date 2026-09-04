## Summary

<一句话描述本次 MHTML 导出变更>

## Changed files

- `src/session_browser/web/mhtml.py`
- `java/web/src/main/resources/templates/...`
- `java/web/src/main/resources/static/...`
- `tests/backend/test_mhtml_export.py`
- ...

## Decisions

- <关键设计决策及其理由，例如内联策略、脱敏规则、大小限制等>

## Gates

| Gate | Result |
|---|---|
| `webResourceContracts` | <PASS/BLOCKED/FAIL/NOT_RUN> |
| `browserBehaviorTests` | <PASS/BLOCKED/FAIL/NOT_RUN> |
| fixture-based 导出测试 | <PASS/BLOCKED/FAIL/NOT_RUN> |
| `agentConfigurationPolicy` | <PASS/BLOCKED/FAIL/NOT_RUN> |

## Risks

- <离线交互保真风险、敏感字段泄露风险、导出文件大小风险或 none>

## Follow-up

- <后续事项或 none>
