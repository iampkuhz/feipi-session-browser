# Checks 维护说明

这里保存“仓库必须满足什么条件”的小型检查。最简单的理解方式是：

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
- `CheckResult` 没有诊断表示通过；有诊断表示失败。Check ID 和最终输出格式由共享 CLI 统一处理。

## 目录怎么找

- `agent/`：Agent 入口、permission、共享规约、skill registry 和 handoff。
- `privacy/`：个人路径、真实 session fixture 和类密钥内容。
- `repository/`：Git、仓库结构、测试纪律、验收契约和路径路由。
- `source/`：源码语言、注释语言和产品 Python 边界。
- `web/`：CSS、JavaScript、模板和 Session Detail 静态契约。
- `web/baselines/`：仅保存 Web 检查使用的已审计基线。

根目录中的 `_framework.py`、`_registry.py`、`__main__.py` 是共享基础设施，不是领域 Check，因此
不使用 `check_` 前缀。

## 如何运行

所有检查都通过同一个命令行入口运行：

```bash
python3 -m scripts.checks agent.skill-registry
python3 -m scripts.checks repository.dead-command-reference
python3 -m scripts.checks web.css-ownership
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

## 新增或删除 Check

1. 新增一个 `check_<subject>.py`，只公开 `check(arguments)`。
2. 在 `_registry.py` 增加唯一的 ID/module pair。
3. 如需加入质量流程，只在 `config/gates.yaml` 声明 Gate、路径 trigger 和 command。
4. 同批增加成功、真实失败和边界 contract。
5. 运行定向测试和 required Gate。

删除时反向删除 `config/gates.yaml` 声明、`_registry.py` registration、实现、测试和调用引用。移动或
改名时必须一次更新全部 caller，旧路径直接删除，不保留 wrapper、re-export 或旧 ID alias。
