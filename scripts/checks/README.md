# Checks 维护说明

这里仅保存共享 Python Check CLI 及其 leaf，不是所有 Gate 实现的总目录。

## 先判断 owner，再打开文件

先在 `config/gates.yaml` 查 Gate declaration：

- `gradle.java_rules`：到 `java/tests/quality-gates/` 查 Java registry 和对应 rule。JVM 源码、template、
  CSS、静态资源等 Web source 语义规则优先由 Java rule 所有。
- `command.argv` 包含 `-m scripts.checks <check-id>`：才到本目录查 Python registry 和 leaf。Git、
  OpenSpec、隐私、Agent 契约及跨语言规则适合留在这里。
- 只有 `gradle.tasks`：到对应 Gradle task，不要在这里增加同义 Python check。

Check ID 的数量和清单只以 `_registry.py` 为真相，`python3 -m scripts.checks --help` 会从 registry
动态列出；本文不手写数量或完整清单。

确认 owner 属于 Python Check CLI 后，最简单的理解方式是：

```text
一个 check_*.py 文件  = 一个 Checker 实现
check(arguments)      = 唯一 public 方法
_开头的函数           = 文件内部实现
_registry.py          = Check ID 到实现文件的路由表
__main__.py           = 唯一命令行入口
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

- 其他函数使用 `_` 前缀。它们可以负责读取文件、解析配置或判断一条规则，但不是执行入口。
- leaf 文件不包含 `main()` 或 `if __name__ == '__main__'`，也不能单独充当命令行程序。
- leaf 文件不带 shebang 或 executable bit；文件路径不是兼容命令，诊断必须使用共享 Check CLI。
- `CheckResult` 没有诊断表示通过；有诊断表示失败。Check ID 和最终输出格式由共享 CLI 统一处理。

## Python leaf 目录怎么找

- `agent/`：Agent 入口、permission、共享规约、skill registry 和 handoff。
- `privacy/`：个人路径、真实 session fixture 和类密钥内容。
- `repository/`：Git、仓库结构、测试纪律、验收契约和路径路由。
- `source/`：生产 Python/shell 注释、仓库语言政策和产品 Python 边界。
- `web/`：仍由 Python 所有的 JavaScript action handler 与 Session Detail 静态契约。已迁移的
  JVM/Web resource 语义规则由 catalog Gate 和 Java quality-gates 管理，不在共享 Check CLI 重复注册。

根目录中的 `_framework.py`、`_registry.py`、`__main__.py` 是共享基础设施，不是领域 Check，因此
不使用 `check_` 前缀。

## 如何运行

所有检查都通过同一个命令行入口运行：

```bash
python3 -m scripts.checks agent.skill-registry
python3 -m scripts.checks repository.dead-command-reference
python3 -m scripts.checks web.session-detail-static
```

成功时只输出：

```text
[<check-id>] PASS
```

失败时逐条输出：

```text
[<check-id>] FAIL: <位置和原因>
```

不要直接运行领域文件。最终质量验证仍使用：

```bash
python3 scripts/gates/cli.py --tier required
```

## 新增或删除 Python Check

1. 先确认规则属于 Git/OpenSpec/隐私/Agent 契约或跨语言边界，不应由 Java rule/Gradle task 所有。
2. 新增一个 `check_<subject>.py`，只公开 `check(arguments)`。
3. 在 `_registry.py` 增加唯一的 ID/module pair。
4. 如需加入质量流程，只在 `config/gates.yaml` 增加一个 Gate declaration、target、路径 trigger 和
   `scripts.checks` command。
5. 同批增加成功、真实失败和边界 contract，运行受影响 target 与 required Gate。
6. 负向搜索确认没有第二 owner、旧 ID 或旧路径。

删除时反向删除 `config/gates.yaml` 声明、`_registry.py` registration、实现、测试和调用引用。移动或
改名时必须一次更新全部 caller，旧路径直接删除，不保留 wrapper、re-export 或旧 ID alias。
