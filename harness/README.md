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
2. **定位一个失败 Gate：** 先查 [`config/gates/README.md`](../config/gates/README.md) 的 42 Gate 使用手册，
   再打开对应领域 YAML，按 typed run 路由到 Java rule、Python check、Gradle task、tool 或固定 suite；
   实现入口与 `gradle`/`process` 执行通道必须分开，详细定位见 [`scripts/gates/README.md`](../scripts/gates/README.md)。
3. **修改 Agent/Harness 约束：** 先读本目录对应 manifest，再按 `skill-registry.yaml` 进入唯一 skill
   真源；不要从客户端目录反向推断共享规则。

本目录不保存 Gate matrix，也不保存运行状态、历史结果或当前 Session 进度。Gate 执行清单从
`config/gates.yaml` 根索引、领域分片与 CLI 派生；target 是 changed path 激活的可多选验证场景，
选择顺序为 path rule targets、Gate target rule/order/pattern、tier、plan。人类精简目录位于
[`config/gates/README.md`](../config/gates/README.md)，单次运行
证据由 Gate artifact 所有。
