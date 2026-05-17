# Feipi Session Browser

独立会话浏览器项目，用于索引和分析 Claude Code、Codex、Qoder 等本地 agent 会话数据。详细工程约束见 `AGENTS.md`。

## 快速入口

| 命令 | 用途 |
|------|------|
| `./scripts/session-browser.sh test` | 运行产品测试 |
| `./scripts/session-browser.sh serve` | 启动本地服务 |
| `./scripts/session-browser.sh scan` | 扫描会话数据 |
| `bash scripts/harness/doctor.sh` | Harness 检查 |
| `/change <需求路径>` | **功能工作默认入口** |

## OpenSpec 变更流

**所有非平凡变更必须走 OpenSpec 流程：**

1. 用 `/change <需求或prompt路径>` 启动变更，在本地创建 `openspec/changes/<change-id>/`
2. 当前行为记录在 `openspec/specs/`，提议行为记录在 `openspec/changes/<change-id>/specs/`
3. 变更激活时写入 `.agent/active_change.json`，子 agent 通过此文件继承上下文
4. 受保护文件编辑需要活跃变更（由 PreToolUse hooks 强制执行）
5. 按 `openspec/changes/<change-id>/tasks.md` 逐条实现
6. 完成后将最终行为同步至 `openspec/specs/` 作为长期真相

详细生命周期：`harness/workflow/openspec-change-lifecycle.md`
openspec 配置与 change skill：`openspec/README.md`

**领域扩展阅读：**
- UI 工作：`harness/context/ui-context.md` + `docs/ui/hifi/README.md`
- MHTML 导出：`harness/context/mhtml-context.md`

## 默认质量门

```bash
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/harness/check_no_unfinished_markers.py
python3 scripts/harness/validate_task_files.py
```

有产品测试时一并运行。

## Claude Code 约束

- 不修改或提交 `.claude/settings.local.json`、`.mcp.json`。
- 不读取或输出真实 session 大文件全文；需要样本时只抽取必要片段。
- 不回滚用户未提交改动。
- 结束前检查 `git status --short`，确认没有缓存、数据、密钥、index 被纳入。

## Agent 规则

1. 从 `openspec/specs/` 获取当前真相
2. 每个非平凡变更使用 `openspec/changes/<change-id>/`
3. 保持任务文件小巧、串行、可独立验证
4. 绝不覆盖用户本地设置
5. 除非变更明确要求，否则保留现有产品代码
6. 汇报完成前先验证
