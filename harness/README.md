# Harness 机器契约

`harness/` 只维护机器可读契约与本索引：

- `manifest.yaml`：公开入口与仓库级约定。
- `agent-runtime.manifest.yaml`、`agent-policy.manifest.yaml`：Runtime/策略真相。
- `context/routes.yaml`、`rules/trigger-policy.yaml`：最小上下文与触发规则。
- `skill-registry.yaml`、`subagents/catalog.yaml`：Skill/Subagent registry。

唯一人类 Runtime 说明见 `docs/agent-runtime.md`；公开命令从 `scripts/README.md` 开始。
