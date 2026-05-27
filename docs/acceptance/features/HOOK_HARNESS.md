# Hook/Harness 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | Claude hook 策略、Stop hook 质量门禁、质量报告生成 |
| 关联源码 | `scripts/claude_hooks/`、`scripts/agent_hooks/`、`scripts/hooks/`、`scripts/quality/` |
| 关联测试 | `tests/hooks/` 下 6 个文件（22 测试函数）、`tests/quality/` 下 7 个文件（238 测试函数） |
| 主要风险 | Stop hook 误判导致合法操作被阻断；质量门禁规则与最新 UI 布局不匹配 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| HOOK-HARNESS-001 | P0 | data | Claude hook Bash 命令策略 | 测试 Bash 命令分类逻辑 | 允许的命令放行，禁止的命令拦截 | pytest | — | `tests/hooks/test_claude_hooks_bash_policy.py` |
| HOOK-HARNESS-002 | P0 | data | Claude hook 分类逻辑 | 测试 hook 事件分类器 | 不同类型事件分类到正确类别 | pytest | — | `tests/hooks/test_claude_hooks_classify.py` |
| HOOK-HARNESS-003 | P0 | data | Claude hook 证据收集 | 测试 hook 证据收集流程 | 证据文件写入正确路径，内容完整 | pytest | — | `tests/hooks/test_claude_hooks_evidence.py` |
| HOOK-HARNESS-004 | P0 | data | Claude hook 文件策略 | 测试 hook 文件操作策略 | 允许/禁止的文件操作分类正确 | pytest | — | `tests/hooks/test_claude_hooks_file_policy.py` |
| HOOK-HARNESS-005 | P0 | data | Claude hook 输入输出 | 测试 hook IO 处理 | hook 输入解析正确，输出格式符合预期 | pytest | — | `tests/hooks/test_claude_hooks_hook_io.py` |
| HOOK-HARNESS-006 | P0 | data | Stop hook 质量门禁 | 测试 Stop hook 质量门禁逻辑 | 有变更时要求 summary artifact，无变更时通过 | pytest | — | `tests/hooks/test_stop_quality_gate.py` |
| HOOK-HARNESS-007 | P0 | data | 质量报告生成 | 测试质量报告生成器 | 生成的报告含所有必需章节，JSON 格式正确 | pytest | — | `tests/quality/test_generate_quality_report.py` |
| HOOK-HARNESS-008 | P0 | data | 新质量门禁规则 | 测试新增的质量门禁规则 | 规则按预期触发，PASS/FAIL 判定正确 | pytest | — | `tests/quality/test_new_quality_gates.py` |
| HOOK-HARNESS-009 | P0 | data | 质量产物结构 | 测试质量产物目录结构 | 产物按 session/change-id 组织，路径正确 | pytest | — | `tests/quality/test_quality_artifact.py` |
| HOOK-HARNESS-010 | P0 | data | 质量门禁运行器 | 测试质量门禁运行器 | 运行器调用正确的检查函数，返回 status | pytest | — | `tests/quality/test_quality_gate_runner.py` |
| HOOK-HARNESS-011 | P0 | data | 仓库精简契约 | 测试仓库精简规则 | 精简后保留必要文件，移除临时/缓存文件 | pytest | — | `tests/quality/test_repo_slimming_contract.py` |
| HOOK-HARNESS-012 | P0 | data | 必需质量门禁运行 | 测试必需门禁运行逻辑 | 标记为必需的门禁必须通过才能继续 | pytest | — | `tests/quality/test_run_required_quality_gates.py` |
| HOOK-HARNESS-013 | P1 | data | 静态契约检查 | 测试静态契约验证 | 模板/CSS/JS 文件结构符合契约规则 | pytest | — | `tests/quality/test_static_contract.py` |
| HOOK-HARNESS-014 | P1 | data | Harness 结构验证 | 测试 harness 目录结构 | harness/manifest.yaml、workflow/、quality/ 目录存在且结构正确 | pytest | — | `scripts/harness/validate_harness_structure.py` |
| HOOK-HARNESS-015 | P1 | data | OpenSpec 布局验证 | 测试 OpenSpec 目录布局 | openspec/ 下 specs/changes/ 目录结构正确 | pytest | — | `scripts/harness/validate_openspec_layout.py` |
