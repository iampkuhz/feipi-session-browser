# 变更报告 — Session Ingestion / Token Attribution

> 完成变更后使用此模板写报告。

## 变更摘要

| 字段 | 值 |
|------|------|
| change_id | `<id>` |
| skill | `feipi-session-ingestion-dev` |
| status | `completed` / `partial` / `blocked` |
| date | YYYY-MM-DD |

## 变更内容

<!-- 列出修改的文件和变更类型 -->

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| | 新增 / 修改 / 删除 | |

## Token 归因影响

<!-- 如果变更影响 token 计算，说明影响范围 -->

- 影响的字段：
- 影响的平台：
- 向后兼容性：

## 质量门禁

| 门禁 | 状态 | 输出 |
|------|------|------|
| `./scripts/session-browser.sh test` | ✅ / ❌ | |
| `./gradlew check` | ✅ / ❌ | |
| `python3 scripts/gates/cli.py --mode incremental` | ✅ / ❌ | |

## 风险

<!-- 列出已知风险或无风险 -->

## 后续事项

<!-- 列出后续需要做的事或无 -->
