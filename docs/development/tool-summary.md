# 工具动作摘要

轮次汇总按类别合并，保留类别首次出现的顺序；一次不加计数，例如 `读取 × 2 · 搜索 · JavaScript`。同一模型调用声明多项工具时，执行区把它们归在同一调用下。类别计数不合并工具记录，每条记录仍可按自己的 ID 查看 Input 和 Result。命令、脚本、路径和参数在原文中查看，不进入工具摘要。

## 分类优先级

类别从已有来源声明中计算，和脱敏、截短后的显示预览分别保存；不从预览反推原输入。单个输入超过 64 Ki 字符时，不解析参数，仅依据已知工具名降级。

1. **明确的工具名优先。** 大小写不敏感，双下划线命名空间使用最后一个 `__` 后的完整名称匹配；点分命名空间仅匹配明确列出的工具（如 `functions.exec`、`tools.exec_command`）。比如 `mcp__files__read_file` 是「读取」；`Grep` 是「搜索」，即便搜索参数是 `python`。写入和编辑分开：`Write` 是「写入」，`apply_patch` 是「编辑」。
2. **已知包装工具只识别固定入口。** `exec` 中，`text(await tools.exec_command(...))` 或直接 `await tools.exec_command(...)` 归 Shell；其他 `exec` 及 `node_repl` 归 JavaScript。不从字符串或任意脚本正文推断内部调用。`exec_command`/ `Bash` 默认是 Shell；命令直接以 `python3`、`/usr/bin/python3`、`node` 或 `deno` 启动时，归对应解释器。`printf x; node task.js` 仍是 Shell。分类不执行或完整解析命令。
3. **等待和发送输入分开。** `write_stdin` 只有明确空输入轮询才是「等待」，发送字符归「进程输入」；`wait` 的顶层布尔值 `terminate: true` 归「终止」，嵌套或字符串值不算。缺少可用参数时只依据工具名，不猜隐藏命令。
4. **没有可靠匹配时为「其他工具」。** 不把未知名称、输入内容或路径当类别输出。Agent 调度、网页类也只识别固定工具名。

## 新增类别

修改 `ToolActionCategory` 的类别键、显示标签和匹配规则，同时更新 `lazy_rounds.js` 的标签表。筛选选项由已加载类别生成，无需修改固定下拉选项。添加一个命中示例及一个近似但不应匹配的示例；更新 Java 分类与轮次汇总测试，必要时补 Playwright 筛选、同调用归属及 Input/Result 原文断言。测试只用合成数据。
