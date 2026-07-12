# Hook/Harness 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 平台 Hook adapter、checkout writer lease、Stop/finalize 与质量报告 |
| 关联源码 | `scripts/agent_runtime/`、`scripts/harness/`、`scripts/hooks/`、`scripts/checks/` |
| 关联测试 | `tests/agent_runtime/`、`tests/gates/`、`tests/test_hook_payload_compat.py`、`tests/test_sessionctl_worktree.py`、`tests/test_stop_entry_runtime_report.py` |
| 主要风险 | 平台 payload 漂移、同 checkout 双写、Stop 伪 PASS、错误集成或删除 provider checkout |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| HOOK-HARNESS-001 | P0 | data | Hook Bash 命令策略 | 表驱动测试 Bash 命令策略 | 允许的命令放行，禁止的命令拦截，危险管道给出 warning | pytest | — | `tests/agent_runtime/test_hook_lifecycle.py::test_bash_policy_matrix` |
| HOOK-HARNESS-002 | P0 | data | changed-files 分类逻辑 | 表驱动测试 planner 分类器 | 不同类型路径分类到正确类别和 target | pytest | — | `tests/agent_runtime/test_hook_lifecycle.py::test_changed_path_classification` |
| HOOK-HARNESS-003 | P0 | data | Hook 证据收集 | 测试 JSONL evidence 公共读写流程 | 证据写入 runtime 路径且内容完整 | pytest | — | `tests/agent_runtime/test_hook_lifecycle.py::test_changed_file_evidence_is_jsonl` |
| HOOK-HARNESS-004 | P0 | data | Hook 文件策略 | 表驱动测试文件写入策略 | 普通产品文件触发 Gate，runtime 产物仅给出 warning | pytest | — | `tests/agent_runtime/test_hook_lifecycle.py::test_file_policy_matrix` |
| HOOK-HARNESS-005 | P0 | data | Hook 输入输出 | 表驱动测试 payload normalization | Bash、Write payload 正确解析，坏 JSON fail-closed | pytest | — | `tests/agent_runtime/test_hook_lifecycle.py::test_hook_payload_normalization` |
| HOOK-HARNESS-006 | P0 | data | Stop hook Git 变更真相 | 在真实临时 Git 仓库采集 evidence | committed、staged/working、untracked 变更分类正确，Git 失败时 fail-closed | pytest | — | `tests/test_stop_entry_runtime_report.py::test_git_evidence_separates_committed_staged_working_and_untracked` |
| HOOK-HARNESS-007 | P0 | data | Gate 结构化报告 | 测试 `scripts.gates.report` 公共 contract | PASS 输出简洁，FAIL/BLOCKED 保留首因，JSON schema/hash 正确且诊断有界 | pytest | — | `tests/gates/test_receipt.py::test_report_contract_is_bounded_and_actionable` |
| HOOK-HARNESS-008 | P0 | data | 新质量门禁规则 | 测试新增的质量门禁规则 | 规则按预期触发，PASS/FAIL 判定正确 | pytest | — | `tests/quality/test_new_quality_gates.py` |
| HOOK-HARNESS-009 | P0 | data | 质量产物结构 | 测试 Gate service 产物与 receipt | 产物按 change-id 组织，路径正确 | pytest | — | `tests/gates/test_cli.py::test_service_writes_artifact_and_receipt` |
| HOOK-HARNESS-010 | P0 | data | Gate executor | 测试唯一 executor 的命令、超时与状态 | catalog 命令被执行，warning/skip/timeout 不得 PASS | pytest | — | `tests/gates/test_executor.py` |
| HOOK-HARNESS-011 | P0 | data | 仓库精简契约 | 测试仓库精简规则 | 精简后保留必要文件，移除临时/缓存文件 | pytest | — | `tests/quality/test_repo_slimming_contract.py` |
| HOOK-HARNESS-012 | P0 | data | 必需质量门禁运行 | 测试 Gate service fail-closed 逻辑 | required Gate 失败不得生成 PASS receipt | pytest | — | `tests/gates/test_cli.py::test_required_gate_failure_never_writes_pass_receipt` |
| HOOK-HARNESS-013 | P1 | data | 静态契约检查 | 测试静态契约验证 | 模板/CSS/JS 文件结构符合契约规则 | pytest | — | `tests/quality/test_static_contract.py` |
| HOOK-HARNESS-014 | P1 | data | Harness 结构验证 | 测试 harness 目录结构 | harness/manifest.yaml、workflow/、quality/ 目录存在且结构正确 | pytest | — | `scripts/harness/validate_harness_structure.py` |
| HOOK-HARNESS-015 | P1 | data | OpenSpec 布局验证 | 测试 OpenSpec 目录布局 | openspec/ 下 specs/changes/ 目录结构正确 | manual | — | `scripts/openspec/validate_layout.py` |
| HOOK-HARNESS-016 | P0 | integration | Checkout writer 隔离 | 在真实 primary/linked worktree 并发请求 writer lease | 同 checkout 只有一个 writer，不同 checkout 可并行，reader 不占 lease | pytest | A/B | `tests/test_sessionctl_worktree.py::test_checkout_writer_lease_real_concurrency_and_worktree_isolation` |
| HOOK-HARNESS-017 | P0 | integration | Lease fencing 与精确回收 | 验证 epoch/token、heartbeat、stale owner、reclaim 和 release | 旧 fence 不能写入，只处理指定 run/session/checkout 并写审计 | pytest | B | `tests/test_sessionctl_worktree.py::test_writer_lease_fencing_reclaim_heartbeat_and_precise_release` |
| HOOK-HARNESS-018 | P0 | integration | OpenSpec run 级绑定 | 以 Registry run 的 change/session/checkout 校验受保护写入 | 其他 Session 的 change 不能劫持当前 run，branch 名不参与授权 | pytest | C | `tests/test_run_identity_evidence_openspec.py` |
| HOOK-HARNESS-019 | P0 | integration | Bash evidence 身份隔离 | 在不同 Session/agent 下记录 Bash mutation snapshot | evidence 只归属对应 runtime identity，写入仍受 checkout lease 约束 | pytest | D | `tests/agent_runtime/test_hook_lifecycle.py::test_bash_snapshots_are_identity_scoped` |
| HOOK-HARNESS-022 | P0 | integration | Resume、CwdChanged 与 task epoch | 重复五类 surface payload，且在 run-scoped 路径中分离 subagent/epoch | 同 Session+checkout 幂等恢复，跨 checkout 不误绑，新 epoch 不读旧 evidence | pytest | G | `tests/test_hook_payload_compat.py`; `tests/test_run_identity_evidence_openspec.py::test_run_scoped_paths_separate_epochs_and_subagents` |
| HOOK-HARNESS-023 | P0 | integration | 五类平台 Hook parity | 参数化验证五 surface adapter、三平台项目 Hook matrix 与公开入口 | 最小 payload 冷启动、重复 bootstrap、PreTool fail-closed 与 exit code 一致 | pytest | H | `tests/test_hook_payload_compat.py`; `tests/agent_runtime/test_hook_lifecycle.py::test_platform_hook_configuration_matrix`; `tests/agent_runtime/test_hook_lifecycle.py::test_platform_pre_write_entrypoints_fail_closed` |
| HOOK-HARNESS-024 | P0 | integration | Cleanup 安全性 | 对指定 run 执行 dry-run 和 execute | 只释放该 run/lease/evidence，保留 provider checkout、branch、dirty 内容与相邻 run | pytest | I | `tests/test_sessionctl_worktree.py::test_cleanup_releases_exact_run_evidence_and_preserves_provider_checkout` |
