# Gate 诊断分类

本页只提供失败分类，不保存 required Gate 清单。当前 target、Gate、tier、path trigger 与命令
必须从 `scripts/gates/catalog.py` 和 `python3 scripts/gates/cli.py --dry-run` 派生；唯一维护流程见
`scripts/gates/README.md`。

## Required baseline

Stop/handoff 前唯一入口：

```bash
python3 scripts/gates/cli.py --tier required
```

所有已触发 required Gate 必须完成并通过。失败、环境阻断、未运行或 skipped 都不能作为整体
`PASS`。定位单 Gate 时使用结构化报告给出的精确 rerun 命令，修复后仍需重跑 required tier。

## Doctor

`bash scripts/harness/doctor.sh` 是 agent/harness/scripts/skills/OpenSpec 的综合体检入口。
Doctor 负责组合结构、配置、语言、Hook/Runtime 与必要 contract 检查；它不是第二个 Gate catalog。
失败时按输出中的首个具体检查定位，不手工拼接一份“required 列表”。

## Stop

共享 dispatcher 只委托 `scripts/harness/stop_entry.py`，再由
`scripts/agent_runtime/stop/pipeline.py` 执行 identity、lock、evidence、reentry-recovery、gate、
report、finalize。Gate 阶段只调用 `scripts.gates.cli.run_service`。

Stop 失败先判断身份/锁/证据/恢复/执行/报告哪一阶段阻断；不要绕过 Stop 直接把某个 leaf check
成功当成整体 `PASS`。

## 领域分类

- **Hook/Runtime**：平台入口、payload、身份、Registry、writer lease、evidence 或 Stop contract。
- **Harness/OpenSpec**：目录结构、规则同步、active change 或变更生命周期 contract。
- **Java/build**：编译、测试、Javadoc、静态分析、Gradle 配置或发行 task。
- **UI/browser**：模板、CSS、交互、布局、fixture server 或 Playwright contract。
- **数据/隐私**：index、session sample、敏感内容与脱敏 contract。
- **环境**：解释器、依赖、浏览器、网络或外部命令不可用；必须保留 `BLOCKED`。

具体失败属于哪个 Gate、执行什么命令，只从本次 Gate plan 和结构化报告读取。
