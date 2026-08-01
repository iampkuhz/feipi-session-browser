# Harness 机器契约

`harness/` 只维护四个静态、机器可读的仓库级 owner：

- `manifest.yaml`：公开命令与仓库级约定。
- `agent-runtime.manifest.yaml`：客户端拥有生命周期、显式验证与平台入口的最小契约。
- `agent-policy.manifest.yaml`：策略、隐私、结果语义与 subagent protocol。
- `skill-registry.yaml`：跨平台 Skill registry。

仓库不通过平台事件维护开发状态。人类说明见 `docs/agent-runtime.md`；公开命令从
`scripts/README.md` 开始。

## 人类阅读路线

1. **日常开发与验证：** 先读 `scripts/README.md`，只记产品入口和 required Gate。
2. **定位一个失败 Gate：** 先查 `config/gates.yaml`，再按 declaration 路由到 Java rule、Python
   check 或 Gradle task；详细定位见 `scripts/gates/README.md`。
3. **修改 Agent/Harness 约束：** 先读本目录对应 manifest，再按 `skill-registry.yaml` 进入唯一 skill
   真源；不要从客户端目录反向推断共享规则。

本目录不保存 Gate matrix，也不保存运行状态、历史结果或当前 Session 进度。Gate 清单从
`config/gates.yaml` / CLI 派生，单次运行证据由 Gate artifact 所有。
