# Checks 规则边界

`scripts/checks/` 保存 Gate executor 与 doctor 调用的领域检查器和叶子工具。这里定义“检查什么”，
不定义“本次选择哪些 Gate、如何并发执行、是否复用或 overall 是否通过”。

## 职责

- `agent/`：Agent 入口、policy、permission、受保护路径、skill registry 与 handoff 契约。
- `repository/`：仓库结构、索引、忽略文件、测试约束、逃逸率与 acceptance contract。
- `privacy/`：本地路径、真实 session fixture 与类密钥内容边界。
- `source/`：注释语言、仓库语言策略与禁止新增产品 Python 的约束。
- `web/`：CSS、JavaScript、模板、静态资源与 Session Detail 契约；`web/baselines/` 只保存
  Web 规则自身的已审计基线。
- 各领域中的 `check_*.py`：只实现一个可命名的仓库不变量，不提供独立 CLI。
- 各领域中的 `validate_*.py`、报告或测量脚本：封装一个领域验证动作或 artifact contract，
  仍不得选择 quality target 或维护 required Gate 集合。
- `_framework.py`：唯一 `CheckResult`/`Diagnostic` 与领域调用协议。
- `_registry.py`：唯一公开 check ID registry；`__main__.py` 统一参数、状态、诊断和退出码。
- 根目录只保留本 README、package/CLI 入口、共享 framework 与显式 registry。

## 不得承担

单个 check 不得实现以下能力：

- Gate/target/tier 注册、dominance 或 path routing；
- 通用 subprocess 循环、timeout、bounded parallel 或 exclusive resource lock；
- 历史结果复用、跨 Gate cache、overall summary 或 Stop/Registry 状态推进；
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
定位失败时使用 Gate 报告中的共享 CLI rerun command；最终 required 验证显式运行：

```bash
python3 scripts/gates/cli.py --tier required
```

## 变更规则

1. 为规则补对应 contract，覆盖成功、真实失败和边界输入；禁止用 skip 代替 fixture 或环境准备。
2. check 保持单一领域职责、确定性输出和非零失败退出码，不自行降级 error 为 warning。
3. 在 `config/gates.yaml` 维护唯一 Gate registration 与 trigger metadata；`catalog.py` 只负责加载
   和校验声明。
4. 用 `python3 scripts/gates/cli.py --dry-run` 检查 plan，再运行受影响 contract 和 required tier。
5. 删除规则时同时删除 `config/gates.yaml` 声明、适用的 `_registry.py` check registration、孤立
   check、contract 和调用引用；不得保留兼容 wrapper。

当前 Gate 名称、target 与 tier 只能从 `config/gates.yaml` 经 catalog/CLI 派生；本目录 README
不维护静态清单。
