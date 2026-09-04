# Python Checks 维护说明

这里仅保存 Gate recipe 中 `python-check` 类型 `RecipeStep` 的领域规则，不是 Gate 清单。20 个逻辑 Gate、
Trigger 与 TargetPreset 以 `scripts/gates/catalog/` 为唯一真相；CLI 使用方法见 `docs/gates/gate-control-plane.md`。

## 文件与命名

```text
check_protocol.py = CheckResult、CheckStatus、Diagnostic 与调用协议
check_registry.py = Check ID 到唯一实现模块的路由
__main__.py       = Execution 阶段使用的内部进程入口
agent/            = Agent 入口、文档和 Skill registry
privacy/          = 凭据与敏感内容规则
repository/       = 仓库边界、维护语言、测试数据和验收映射
source/           = 源码注释语言规则
```

领域文件固定命名为 `check_<subject>.py`，只公开：

```python
def check(arguments: list[str]) -> CheckResult:
    """解析参数，执行业务规则并返回完整诊断。"""
```

每个实现模块只在 `check_registry.py` 登记一次，每个 Check ID 也只能被一个 Gate 的一个 RecipeStep
拥有。其他函数使用 `_` 前缀；领域文件不带 shebang、`main()` 或独立命令入口，也不负责 Trigger 匹配。

## 当前公开 Check ID

当前 registry 有 12 个内部 Check，其中本次明确命名的责任边界为：

- `agent.entrypoints`：跨客户端 Agent 入口、权限与 runtime 配置。
- `agent.documentation`：Agent 维护文档、受保护路径与 handoff 协议。
- `repository.file-boundary`：仓库文件、退役路径和 Git 追踪边界。
- `repository.maintenance-language`：仓库维护文本语言规则。
- `privacy.credential-leak`：凭据与类密钥内容扫描。
- `source.code-comment-language`：源码注释语言规则。

完整清单动态读取 `check_registry.py`；旧 ID 不提供 alias。

## 执行与状态

维护者只通过顶层 Gate CLI 运行对应 Gate，例如：

```bash
python3 scripts/gates/cli.py run --mode full --gate agentConfigurationPolicy
python3 scripts/gates/cli.py run --mode full --gate repositoryBoundaryAudit
```

Execution adapter 内部调用 `python3 -m scripts.gates.checks <check-id>`。没有诊断为 `PASS`；完整执行后
发现领域违规为 `BLOCKED reason=verification-failed`；输入、依赖或运行时无法形成结论为 `FAIL`。

新增 Check 时必须同批完成：实现文件、`check_registry.py` 唯一登记、Catalog RecipeStep owner、Trigger、
定向测试和维护文档。移动或删除时同步移除所有 caller；不得保留 wrapper、re-export 或旧 ID alias。
