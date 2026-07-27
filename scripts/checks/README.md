# Checks 规则边界

`scripts/checks/` 保存 Gate executor 与 doctor 调用的领域检查器和叶子工具。这里定义“检查什么”，
不定义“本次选择哪些 Gate、如何并发执行、是否复用或 overall 是否通过”。

## 职责

- `check_*.py`：领域函数或小对象，只实现一个可命名的仓库不变量，不提供独立 CLI。
- `run_*.py`、`validate_*.py`、报告或测量脚本：封装一个领域验证动作或 artifact contract，
  仍不得选择 quality target 或维护 required Gate 集合。
- `_framework.py`：唯一 `CheckResult`/`Diagnostic`/`ScanContext` 与领域调用协议。
- `_registry.py`：唯一公开 check ID registry；`__main__.py` 统一参数、状态、诊断和退出码。
- baseline 文件只保存规则自身所需的审计基线，不能保存另一份 Gate/target matrix。

## 不得承担

单个 check 不得实现以下能力：

- Gate/target/tier 注册、dominance 或 path routing；
- 通用 subprocess 循环、timeout、bounded parallel 或 exclusive resource lock；
- receipt、跨 Gate cache、overall summary 或 Stop/Registry 状态推进；
- 平台 Hook payload 解析、writer lease 或 worktree 生命周期；
- 真实 session、密钥、token、个人路径或不可提交运行数据的 fixture 构造。

这些职责分别属于 `scripts/gates/`、客户端/Git、minimal `scripts/harness/` 与测试 support；仓库不再提供 Agent Session Runtime。
不要为单个 check 新增 runner wrapper，也不要让 CI/Stop 直接拼接一组 check 命令。

## 调用与诊断

正常执行与直接诊断都只走共享 CLI：

```bash
python3 -m scripts.checks agent.skill-registry
python3 -m scripts.checks repository.dead-command-reference
python3 -m scripts.checks web.css-ownership
```

Gate catalog/planner 是 trigger 与 applicability 唯一权威；领域 check 不解析 changed-files 来跳过。
`ScanContext` 在同次组合检查中复用文件发现与文本读取。定位失败时使用 Gate 报告中的共享 CLI
rerun command；最终 required 验证显式运行：

```bash
python3 scripts/gates/cli.py --tier required
```

## 变更规则

1. 为规则补对应 contract，覆盖成功、真实失败和边界输入；禁止用 skip 代替 fixture 或环境准备。
2. check 保持单一领域职责、确定性输出和非零失败退出码，不自行降级 error 为 warning。
3. 在 `scripts/gates/catalog.py` 维护唯一 Gate registration 与 trigger metadata。
4. 用 `python3 scripts/gates/cli.py --dry-run` 检查 plan，再运行受影响 contract 和 required tier。
5. 删除规则时同时删除 catalog registration、孤立 check、contract 和调用引用；不得保留兼容 wrapper。

当前 Gate 名称、target 与 tier 只能从 `scripts/gates/catalog.py` 或 `scripts/gates/cli.py` 派生；
本目录 README 不维护静态清单。
