# Deterministic Quality Gate Matrix

## 01. 原则

- required gate 只能是 `PASS|FAIL|BLOCKED|SKIPPED`。
- required gate 出现 `SKIPPED` 时，overall 必须是 `FAIL`。
- required gate 缺失时，overall 必须是 `BLOCKED` 或 `FAIL`。
- 不允许 `score`、`rating`、`qualityScore` 等主观评分字段。
- Stop hook 不跑重型测试，只验证最新 summary artifact。

## 02. 触发矩阵

| 变更路径 | category | target | required gates |
|---|---|---|---|
| `src/session_browser/web/templates/**/*.html` | ui-template | session-detail | pythonCompile, templateContract, staticCssContract, browserLayout, pytest |
| `src/session_browser/web/static/**/*.css` | ui-css | session-detail | pythonCompile, templateContract, staticCssContract, browserLayout, pytest |
| `src/session_browser/web/static/**/*.js` | ui-js | session-detail | pythonCompile, templateContract, staticCssContract, browserLayout, pytest |
| `src/session_browser/**/*.py` | python-src | python-src | pythonCompile, pytest |
| `.claude/settings.json` | claude-config | hook-runtime | settingsJson, bashSyntax, pythonCompile, hookSelfTest, pytest, doctor, repoStructure |
| `.claude/hooks/**` | hook | hook-runtime | settingsJson, bashSyntax, pythonCompile, hookSelfTest, pytest, doctor, repoStructure |
| `scripts/claude_hooks/**` | hook | hook-runtime | settingsJson, bashSyntax, pythonCompile, hookSelfTest, pytest, doctor, repoStructure |
| `scripts/quality/**` | quality-gate | hook-runtime | settingsJson, bashSyntax, pythonCompile, hookSelfTest, pytest, doctor, repoStructure |
| `harness/**` | harness | harness | bashSyntax, pythonCompile, doctor, repoStructure, harnessStructure, openspecLayout |
| `scripts/harness/**` | harness | harness | bashSyntax, pythonCompile, doctor, repoStructure, harnessStructure, openspecLayout |

## 03. 输出路径

```text
tmp/agent_logs/<session>/quality/<change-id>/quality-gate-summary.<target>.json
```
