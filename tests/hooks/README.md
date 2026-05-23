# Hook 场景测试 — 受保护目录

> **本目录受保护。任何修改必须逐文件经用户确认后方可执行。**

## 保护范围

以下文件禁止自动修改（包括 agent 自动编辑、重构、重命名）：

| 文件 | 用途 |
|---|---|
| `test_claude_hooks_bash_policy.py` | Bash 策略校验 |
| `test_claude_hooks_classify.py` | Hook 分类逻辑 |
| `test_claude_hooks_evidence.py` | Evidence 写入验证 |
| `test_claude_hooks_file_policy.py` | 文件读写策略 |
| `test_claude_hooks_hook_io.py` | Hook 输入输出 |
| `test_claude_hooks_stop_policy.py` | Stop/SubagentStop 策略 |
| `test_stop_quality_gate.py` | Stop Hook 质量门 |

## 修改流程

1. **明确指出**要改哪个文件、改什么、为什么改
2. **展示 diff** 或完整变更内容
3. **等待用户逐一确认**每个文件的变更
4. 用户确认后方可执行

## 为什么受保护

Hook 是 Claude Code 运行时的核心安全和质量门，负责：
- 阻止危险命令（`rm -rf`、`force push` 等）
- 保护敏感目录不被误写
- 确保 deterministic quality artifact 在 stop 时验证

误改可能导致破坏性行为被跳过、安全策略失效或质量门降级。

## 对应产品代码

Hook 测试验证的逻辑位于 `scripts/claude_hooks/` 和 `.claude/hooks/claude-hook.sh`。
