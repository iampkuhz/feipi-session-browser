# Harness 机器契约

`harness/` 只维护四个静态、机器可读的仓库级 owner：

- `manifest.yaml`：公开命令与仓库级约定。
- `agent-runtime.manifest.yaml`：客户端拥有生命周期、显式验证与平台入口的最小契约。
- `agent-policy.manifest.yaml`：策略、隐私、结果语义与 subagent protocol。
- `skill-registry.yaml`：跨平台 Skill registry。

仓库不通过平台事件维护开发状态。人类说明见 `docs/agent-runtime.md`；公开命令从
`scripts/README.md` 开始。

## 人类阅读路线

1. **日常开发与验证：** 先读 `scripts/README.md`，只记产品入口和 incremental/full Gate；环境与性能维护才
   显式运行 `python3 scripts/gates/cli.py health`。
2. **定位一个失败 Gate：** 先用 Gate CLI 的 `list/explain/plan`，再查
   [`docs/gates/gate-control-plane.md`](../docs/gates/gate-control-plane.md)，按 Catalog 中的 RecipeStep 路由到 Java rule、Python Check、
   Gradle task、tool 或固定 suite。
3. **修改 Agent/Harness 约束：** 先读本目录对应 manifest，再按 `skill-registry.yaml` 进入唯一 skill
   真源；不要从客户端目录反向推断共享规则。

本目录不保存 Gate matrix，也不保存运行状态、历史结果或当前 Session 进度。Gate 清单只在
`scripts/gates/catalog/` 声明：incremental 由 ChangeSnapshot 匹配 Gate Trigger，full 选择全部 Gate；
TargetPreset 只供维护者显式选择一组 Gate。单次运行证据位于不可覆盖的 `tmp/quality/runs/<run-id>/`。

Harness doctor 是 standalone 只读诊断，并由显式 health 流程调用；它不属于 Gate Catalog，普通
incremental/full、Hook 与 Stop/handoff 都不会隐式运行 doctor 或 health。
