# Harness

本目录只保留当前工程入口。

## 当前真源

- `harness/manifest.yaml`：入口、质量目标和本地文件策略。
- `harness/agent-runtime.md`：Claude Code、Codex、Qoder 共享的 agent 运行契约。
- `scripts/harness/agent_stop_check.py`：三类 agent 共用的 Stop 门禁入口。
- `scripts/harness/doctor.sh`：harness 最小健康检查。
- `scripts/quality/run_quality_gate.py`：质量门执行入口。
- `scripts/quality/quality_targets.py`：质量目标与触发规则。

## 常用命令

```bash
bash scripts/harness/doctor.sh
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/quality/run_quality_gate.py --target acceptance-contracts --change-id local
python3 scripts/quality/run_quality_gate.py --target session-detail
```

质量门输出写入 `tmp/quality/<change-id>/`。运行态日志写入 `tmp/agent_logs/`。
