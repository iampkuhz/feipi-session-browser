# Deterministic Quality Gate

## 01. 禁止事项

- 禁止 LLM 主观评分替代 gate。
- 禁止 `score/rating/qualityScore` 进入 summary。
- 禁止 required gate `SKIPPED` 后 overall PASS。
- 禁止 Stop hook 直接执行 Playwright 或全量 pytest。

## 02. Summary Schema

```json
{
  "schemaVersion": 2,
  "status": "PASS|FAIL|BLOCKED",
  "target": "session-detail",
  "changeId": "change-id",
  "startedAt": "ISO-8601",
  "finishedAt": "ISO-8601",
  "requiredGates": {
    "pythonCompile": "PASS",
    "templateContract": "PASS",
    "staticCssContract": "PASS",
    "browserLayout": "PASS",
    "pytest": "PASS"
  },
  "blockingFailures": [],
  "warnings": [],
  "artifacts": {},
  "gateDetails": []
}
```

## 03. Stop Hook 行为

1. 读取当前 session 的 `changed-files.jsonl`（位于 `tmp/agent_logs/<session>/`）。
2. 找出最近 change-id 的 required target。
3. 检查对应 summary 是否存在。
4. 检查 status 是否 PASS。
5. 检查 finishedAt 是否晚于变更记录。
6. 检查 requiredGates 中没有 SKIPPED。
7. 失败时 exit 2，并给出可执行命令。
