# /openspec-apply

通过按序执行 `tasks.md` 来应用已有的 OpenSpec 变更。

Arguments: `$ARGUMENTS`

规则：

- 先读取 `proposal.md`、`design.md`、`tasks.md` 和差异规格。
- 仅执行下一个未完成的任务，除非明确要求否则不跳过。
- 在 `tasks.md` 中标记已完成的任务。
- 在进入下一个任务前运行任务级验证。
- 不扩大变更范围。
