# Harness 机器契约

`harness/` 只维护四个静态、机器可读的仓库级 owner：

- `manifest.yaml`：公开命令与仓库级约定。
- `agent-runtime.manifest.yaml`：客户端拥有生命周期、显式验证与平台入口的最小契约。
- `agent-policy.manifest.yaml`：策略、隐私、结果语义与 subagent protocol。
- `skill-registry.yaml`：跨平台 Skill registry。

仓库不通过平台事件维护开发状态。人类说明见 `docs/agent-runtime.md`；公开命令从
`scripts/README.md` 开始。
