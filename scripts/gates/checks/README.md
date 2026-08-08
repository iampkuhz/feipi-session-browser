# Checks 维护说明

这里是 Gate service 的 Python leaf 子目录，不是所有 Gate 实现的总目录。完整逻辑 Gate 和触发方式先看
`scripts/gates/README.md`。

## 先判断 owner，再打开文件

先在 `scripts/gates/README.md` 查 20 个逻辑 Gate，再到 `scripts/gates/definitions.py` 查看唯一 recipe。
Composite Gate 的 Python leaf 仍按 step 中的 Check ID 单独分诊断，但 leaf 不是顶层 `--gate` alias：

- recipe 类型是 `java-rule`：到 `java/tests/quality-gates/` 查 Java registry 和对应 rule。JVM 源码、template、
  CSS、静态资源等 Web source 语义规则优先由 Java rule 所有。
- recipe 类型是 `python-check`：才到本目录查 Python registry 和 leaf。Executor 会在内部转换为
  `-m scripts.gates.checks <check-id>`；维护者不要手工调用这一适配器。Git、
  OpenSpec、隐私、Agent 契约及跨语言规则适合留在这里。
- recipe 类型是 `gradle-task`：到对应 Gradle task，不要在这里增加同义 Python check。

当前 registry 有 **12 个内部 Check**。数量和清单只以 `_registry.py` 为真相，并且每个 ID 都必须被 `definitions.py` 中某个 Gate
拥有；禁止注册只能手工执行的旁路 Check。

确认 owner 属于 Python Check 后，最简单的理解方式是：

```text
一个 check_*.py 文件  = 一个 Checker 实现
check(arguments)      = 唯一 public 方法
_开头的函数           = 文件内部实现
_registry.py          = Check ID 到实现文件的内部路由表
__main__.py           = Executor 使用的内部子进程适配器
```

维护者不需要从多个 `main`、`run_check` 或 `validate` 中猜入口。打开任意 `check_*.py` 后，先读文件
顶部的中文说明，再找唯一的 `check(arguments)` 即可。

## 固定文件约定

- 领域检查文件必须命名为 `check_<subject>.py`。
- 每个文件只在 `_registry.py` 登记一次，也只对应一个 Check ID。
- 每个文件只公开：

  ```python
  def check(arguments: list[str]) -> CheckResult:
      """解析参数，执行业务检查并返回全部失败诊断。"""
  ```

- 其他函数使用 `_` 前缀。它们可以负责读取文件、解析配置或判断一条规则，但不是执行入口；每个函数都要用
  一句中文 docstring 说明它与文件主题的关系，复杂分支再补中文行内注释。
- leaf 文件不包含 `main()` 或 `if __name__ == '__main__'`，也不能单独充当命令行程序。
- leaf 文件不带 shebang 或 executable bit；文件路径不是兼容命令，诊断必须通过顶层 Gate CLI 触发。
- `CheckResult` 没有诊断表示通过；有诊断表示失败。Check ID 和最终输出格式由内部适配器统一处理。

## Python leaf 目录怎么找

- `agent/`：Agent runtime policy、document policy 和 skill registry；运行配置与维护文档分开。
- `privacy/`：类密钥与凭据形态内容。
- `repository/`：仓库文件政策、当前源码、测试数据、测试纪律、验收用例和路径路由。
- `source/`：生产 Python/shell 注释、仓库语言政策和产品 Python 边界。
根目录中的 `_framework.py`、`_registry.py`、`__main__.py` 是共享基础设施，不是领域 Check，因此
不使用 `check_` 前缀。

## 如何运行

维护者只运行顶层 Gate CLI；先在 `scripts/gates/README.md` 查 leaf 属于哪个 Gate：

```bash
python3 scripts/gates/cli.py --mode incremental --gate agentPolicy
python3 scripts/gates/cli.py --mode incremental --gate repositoryFilePolicy
python3 scripts/gates/cli.py --mode incremental --gate governanceStructure
```

Executor 内部 leaf 成功时输出：

```text
GATE_RESULT status=PASS check=<check-id>
```

失败时逐条输出：

```text
[<check-id>] BLOCKED|FAIL: <位置和原因>
GATE_RESULT status=BLOCKED|FAIL check=<check-id>
```

不要直接运行领域文件或内部 Check CLI。最终质量验证使用：

```bash
python3 scripts/gates/cli.py --mode incremental
```

## 新增或删除 Python Check

1. 先确认规则属于 Git/OpenSpec/隐私/Agent 契约或跨语言边界，不应由 Java rule/Gradle task 所有。
2. 新增一个 `check_<subject>.py`，只公开 `check(arguments)`。
3. 在 `_registry.py` 增加唯一的 ID/module pair。
4. 同时在 `scripts/gates/definitions.py` 把 leaf 归入一个逻辑 Gate，并同步 Trigger 和
   `scripts/gates/README.md`；禁止只注册、不进入 Gate 的旁路 Check。
5. 同批增加成功、真实失败和边界 contract，运行受影响 Gate 与增量交付检查。
6. 负向搜索确认没有第二 owner、旧 ID 或旧路径。

删除时反向删除 typed declaration、手册行、`_registry.py` registration、实现、测试和调用
引用。移动或改名时必须一次更新全部 caller，旧路径直接删除，不保留 wrapper、re-export 或旧 ID alias。
