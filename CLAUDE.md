# Feipi Session Browser

独立会话浏览器项目。详细约束见 `AGENTS.md`。

## 快速入口

- 工具使用规范：`docs/governance/tool-usage.md`
- 本地测试：`./scripts/session-browser.sh test`
- 本地服务：`./scripts/session-browser.sh serve`
- Harness 检查：`bash scripts/harness/doctor.sh`

## Claude Code 注意事项

- 不修改或提交 `.claude/settings.local.json`、`.mcp.json`。
- 不读取或输出真实 session 大文件全文；需要样本时只抽取必要片段。
- 不回滚用户未提交改动。
- 结束前检查 `git status --short`，确认没有缓存、数据、密钥、index 被纳入。

## OpenSpec Workflow

This repository uses an OpenSpec-first Claude Code workflow. Read these first:

- `harness/README.md` — workflow, context packs, prompts, quality gates
- `harness/workflow/openspec-change-lifecycle.md` — propose → design → tasks → implement → validate → archive
- `harness/context/repo-context.md` — repository context
- `openspec/README.md` — spec-driven development layout

For UI work, also read `harness/context/ui-context.md` and `docs/ui/hifi/README.md`.
For MHTML export work, also read `harness/context/mhtml-context.md`.

### Non-negotiable workflow

- No feature, refactor, or bugfix implementation without an OpenSpec change under `openspec/changes/<change-id>/`.
- Current behavior belongs in `openspec/specs/`.
- Proposed behavior belongs in `openspec/changes/<change-id>/specs/`.
- Implement work by walking `openspec/changes/<change-id>/tasks.md` sequentially.
- Keep main context small. Delegate bounded inspection/review to project subagents when useful.
- Do not edit `.claude/settings.local.json`.

### Default quality gates

```bash
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/harness/check_no_unfinished_markers.py
python3 scripts/harness/validate_task_files.py
```

If product tests exist, run them as well.
