# Feipi Session Browser

独立会话浏览器项目，用于索引和分析 Claude Code、Codex、Qoder 等本地 agent 会话数据。

## 启动协议

1. 先读 `AGENTS.md`，获取仓库级约束、OpenSpec 流程和质量门。
2. 根据任务类型按下方路由加载最少必要文件。
3. 不要预读全量 `harness/`、`openspec/`、`tests/`。

## 任务路由

| 任务类型 | 先读 |
|---|---|
| 功能开发 | `openspec/specs/` + `openspec/changes/<id>/tasks.md` |
| UI 修改 | `harness/context/ui-context.md` |
| MHTML 导出 | `harness/context/mhtml-context.md` |
| Harness/Workflow 修改 | `harness/manifest.yaml` + `harness/workflow/` |
| 产品代码修改 | `src/session_browser/` 相关模块 |
| 测试修改 | `tests/` + `scripts/session-browser.sh test` |
| 文档修改 | `README.md` |

## Claude 执行约束

- 对多步骤改造，先给计划，再改文件。
- 大任务使用 subagent 隔离上下文；主 agent 负责任务分派、验收和总结。
- 串行任务逐项执行，不跳步，不 busy-wait。
- 不修改 `.claude/settings.local.json` 和 `.mcp.json`，除非用户明确要求。
- 不读取或输出真实 session 大文件全文；需要样本时只抽取必要片段。
- 不回滚用户未提交改动。
- 不把本地绝对路径、密钥、token 写入仓库文档。

## 质量门禁

完成后必须运行适用的验证：

| 改动类型 | 验证命令 |
|---|---|
| 任何改动 | `bash scripts/harness/doctor.sh` |
| Harness 结构 | `python3 scripts/harness/validate_harness_structure.py` |
| OpenSpec 布局 | `python3 scripts/harness/validate_openspec_layout.py` |
| 完成标记 | `python3 scripts/harness/check_no_unfinished_markers.py` |
| 任务文件 | `python3 scripts/harness/validate_task_files.py` |
| 产品测试 | `./scripts/session-browser.sh test` |

## UI 质量门禁

修改 `src/session_browser/web/templates/`、
`src/session_browser/web/static/*.css` 或 `src/session_browser/web/static/js/` 时，
运行：

```bash
python3 scripts/quality/run_quality_gate.py --target session-detail
```

UI 任务完成的前提是 `.agent/quality/<change-id>/quality-gate-summary.json`
报告 `status: PASS`。

详见：
- `harness/quality/quality-gate-matrix.md`
- `harness/quality/ui-layout-contract.md`
- `harness/quality/ui-gate-diagnostic.md`

## 规约文件语言策略

- **所有规约/规格/提示词/模板/流程文档必须中文优先**。
- 仅技术术语（如 `OpenSpec`、`PreToolUse`）、代码标识符、外部工具名称可保留英文。
- 新建 `.md` 规约文件默认使用中文编写。
- 详见 `AGENTS.md` 中的「规约文件语言策略」章节。

## 输出要求

- 面向用户输出默认简体中文。
- 结束前检查 `git status --short`，确认没有缓存、数据、密钥、index 被纳入。
- 总结必须包含：改了什么、为什么、验证结果、剩余风险。
