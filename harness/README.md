# Harness

本目录包含用于在 Claude Code 下保持仓库可控性的工程流程。

## 01. 目标

本目录描述 `feipi-session-browser` 的 Claude Code 本地工程化改造约束：

- Hook runtime 单入口
- `tmp/agent_log/` 运行态目录
- deterministic quality gate
- 高权限、强质量
- 文档、脚本、测试三者一致

## 02. 目录

```text
harness/
  README.md
  manifest.yaml
  context/          # 渐进式加载上下文包
  quality/
    quality-gate-matrix.md
    deterministic-quality-gate.md
  workflow/
    hook-runtime-lifecycle.md
    openspec-change-lifecycle.md   # 原有
    subagent-execution.md           # 原有
```

## 03. 运行态目录

新代码默认只写：

```text
tmp/agent_log/
```

`.agent/` 只作为 legacy 只读兼容路径。

## 04. Hook Runtime

入口：

```text
.claude/hooks/claude-hook.sh
```

Python 逻辑：

```text
scripts/claude_hooks/
```

详细生命周期见 `workflow/hook-runtime-lifecycle.md`。

## 05. Quality Gate

显式运行：

```bash
python3 scripts/quality/run_quality_gate.py --target session-detail --change-id <change-id>
python3 scripts/quality/run_quality_gate.py --target python-src --change-id <change-id>
python3 scripts/quality/run_quality_gate.py --target hook-runtime --change-id <change-id>
python3 scripts/quality/run_quality_gate.py --target harness --change-id <change-id>
```

输出：

```text
tmp/agent_log/quality/<change-id>/quality-gate-summary.<target>.json
tmp/agent_log/quality/<change-id>/gate-details.<target>.json
```

Stop hook 只检查 artifact，不跑重型测试。
详见 `quality/deterministic-quality-gate.md` 和 `quality/quality-gate-matrix.md`。
