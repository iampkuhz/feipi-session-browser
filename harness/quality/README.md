# 质量门禁

成功报告前的确定性验证。
LLM 诊断为按需/可选，不得接入 hook。
运行时产物位于 `tmp/quality/<change-id>/`，非源文档。

## 结构

| 文件 | 用途 |
|---|---|
| [quality-gate-matrix.md](./quality-gate-matrix.md) | 各类变更运行哪些门禁 |
| [ui-layout-contract.md](./ui-layout-contract.md) | 会话详情页布局硬指标 |
| [ui-gate-diagnostic.md](./ui-gate-diagnostic.md) | 按需 LLM 诊断边界 |
| [gates.yaml](./gates.yaml) | Harness 门禁配置 |
| [gates.md](./gates.md) | 门禁定义与状态 |

## 运行门禁

```bash
# 统一运行器
python3 scripts/quality/run_quality_gate.py --target session-detail

# 单个门禁
python3 scripts/quality/check_session_detail_static.py
python3 -m pytest tests/test_session_detail_layout_contract.py
python3 scripts/quality/run_session_detail_layout_gate.py --url ...

# Stop hook 强制执行
python3 scripts/hooks/stop_quality_gate.py
```

## 按需 LLM 诊断

```
/diagnose-ui-gate
```

读取失败的门禁产物并建议最小修复。它不是门禁——不能通过或阻塞 stop hook。
