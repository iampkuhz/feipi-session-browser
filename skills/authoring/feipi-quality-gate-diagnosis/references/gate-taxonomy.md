# Gate 诊断分类

本页只提供失败分类，不保存 required Gate 清单。当前 target、Gate、tier、path trigger 与命令必须从 `scripts/gates/catalog.py` 和 `python3 scripts/gates/cli.py --dry-run` 派生。

## Required baseline

显式入口：

```bash
python3 scripts/gates/cli.py --tier required
```

所有已触发 Gate 必须完成并通过。失败、环境阻断、未运行、warning 或 skipped 都不能作为整体 `PASS`；`NOT_TRIGGERED` 单独报告。

## Doctor

`bash scripts/harness/doctor.sh` 检查 minimal harness、agent/skill、OpenSpec 与工具环境。Doctor 不是第二个 Gate catalog，也不得要求 Hook/Session Runtime 文件存在。

## 领域分类

- **Harness/OpenSpec**：目录结构、agent policy、skill registry、active change 或规格 contract。
- **Gate framework**：catalog、planner、executor、resource lock、receipt 或报告。
- **Java/build**：编译、测试、Javadoc、静态分析、Gradle 配置或发行 task。
- **UI/browser**：模板、CSS、交互、布局、fixture server 或 Playwright contract。
- **数据/隐私**：index、session sample、敏感内容与脱敏 contract。
- **环境**：解释器、依赖、浏览器、网络或外部命令不可用；必须保留 `BLOCKED`。

仓库不再维护 Hook payload、Session Registry、writer lease、Stop controller 或自动 integration 分类。具体失败属于哪个 Gate、执行什么命令，只从本次 Gate plan 和结构化报告读取。
