## Summary

概述本次隐私脱敏变更的目的和范围。

## Changed files

列出所有修改的文件路径和变更类型（新增/修改/删除）。

## Decisions

记录本次变更中做出的关键决策：

- 哪些字段标记为敏感。
- 使用什么脱敏策略（隐藏/替换/省略）。
- fixture 是否 synthetic。
- 是否新增 gate。

## Gates

列出运行的 gate 及结果：

- `repository.no-real-session-fixtures` — PASS/FAIL
- `security.secret-like-content` — PASS/FAIL
- `agent.skill-registry` — PASS/FAIL
- `agent.runtime-manifest` — PASS/FAIL
- `doctor.sh` — PASS/FAIL

未运行的 gate 必须写明原因。

## Risks

列出残留风险和后续 TODO：

- 仍可能存在的敏感字段。
- 需要人工复核的内容。
- 后续需要增强的检查。

## Follow-up

列出后续需要跟进的事项：

- 是否需要更新脱敏策略。
- 是否需要补充更多 synthetic fixture。
- 是否需要增强 gate 检测规则。
