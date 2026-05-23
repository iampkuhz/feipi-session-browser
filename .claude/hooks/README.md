# Claude Hook Runtime

## 01. 入口

所有 Claude Code hook 均统一进入：

```bash
.claude/hooks/claude-hook.sh <event>
```

该脚本只负责：

1. 定位仓库根目录。
2. 设置 `PYTHONPATH`。
3. 设置默认 `FEIPI_AGENT_LOG_DIR=tmp/agent_log`。
4. 调用 `python3 -m scripts.claude_hooks.main <event>`。
5. 透传 exit code。

## 02. 业务逻辑位置

业务逻辑统一放在：

```text
scripts/claude_hooks/
```

不再把复杂逻辑散落在 `.claude/hooks/*.sh`、`scripts/hooks/*.py`、`scripts/agent_hooks/*.py`。

## 03. 权限原则

- 仓库内读写默认允许。
- Hook 不做白名单式正常开发限制。
- hard block 只用于少数危险命令和敏感数据泄露场景。
- deterministic quality gate 由显式命令生成 artifact。
- Stop hook 只检查 artifact，不跑重型测试。

## 04. 运行态目录

默认写入：

```text
tmp/agent_log/
```

`.agent/` 只作为 legacy 只读兼容路径。
