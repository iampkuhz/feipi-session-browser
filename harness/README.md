# Harness

本目录只保留当前工程入口。

Scripts 的公开 allowlist 与 Hook → Runtime → Stop → Gate 全链路从 `scripts/README.md` 开始；
本目录只保存跨平台契约、上下文与工作流，不维护第二份 Gate/target 清单。

## 当前真源

- `skills/authoring/feipi-openspec-orchestrate-change/SKILL.md`：OpenSpec 变更编排 skill 真源。
- `.agents/skills/feipi-openspec-orchestrate-change`：Codex repo-scope skill 发现入口，链接到共享真源。
- `harness/manifest.yaml`：入口、质量目标和本地文件策略。
- `harness/agent-runtime.md`：Claude Code、Codex、Qoder 共享的 agent 运行契约。
- `harness/context/`：按需加载的仓库和 UI 上下文路由。
- `harness/workflow/`：OpenSpec 与 subagent 执行规约。
- `harness/quality/`：质量门语义、target 路由和 Stop 门禁解释。
- `scripts/harness/stop_entry.py`：三类 agent 共用的薄 Stop 入口；唯一七阶段业务位于 `scripts/agent_runtime/stop/pipeline.py`。
- `scripts/harness/doctor.sh`：harness 最小健康检查。
- `scripts/gates/cli.py`：质量门执行入口。
- `scripts/gates/catalog.py`：质量目标与触发规则。
- `scripts/agent_runtime/README.md`：事件、身份、Registry、writer lease 与 Stop 七阶段阅读路线。
- `scripts/gates/README.md`：唯一 Gate service、状态语义与新增/修改/删除流程。
- `scripts/checks/README.md`：领域检查器的职责边界。

## 常用命令

```bash
bash scripts/harness/doctor.sh
python3 scripts/harness/validate_harness_structure.py
python3 scripts/openspec/validate_layout.py
python3 scripts/gates/cli.py --tier quick --dry-run
python3 scripts/gates/cli.py --tier required
```

质量门输出写入 `tmp/quality/<change-id>/`。运行态日志写入 `tmp/agent_logs/`。
