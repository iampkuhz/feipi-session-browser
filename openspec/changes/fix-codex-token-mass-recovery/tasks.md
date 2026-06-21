# 任务：修正 Codex Token Mass 归因恢复

按顺序推进任务。每个勾选项完成后记录验证证据。

## 阶段 1：规划与样例审查

- [x] 1.1 审查用户提供的新版 `codex.md`、目标 session 详细分析和 `normalized.json`。
  - 验证：PASS — 三份材料核心逻辑一致；`normalized.json` 可作为中间结构参考，但缺少 evidence/diagnostics/source-unit 细节，不作为最终完整契约。

- [x] 1.2 创建 OpenSpec change 并运行规划验证。
  - 验证：PASS — `python3 scripts/harness/validate_openspec_layout.py && python3 scripts/openspec/validate_layout.py && python3 scripts/openspec/validate_schema.py && python3 scripts/openspec/validate_active_change.py --change-id fix-codex-token-mass-recovery && python3 scripts/harness/validate_harness_structure.py`。

## 阶段 2：文档与 parser

- [x] 2.1 更新 `docs/agent-token-attribution/codex.md` 为新版通用逻辑。
  - 验证：PASS — 已用 `~/Downloads/codex-5.md` 同步仓库 Codex 通用归因文档。

- [x] 2.2 修正 Codex parser：`tool_search_output` 进入下一 request 的 tool result；subagent call model 使用 turn model。
  - 验证：PASS — 目标样例解析后 C2 request 含 `call_XsbhHJb7vGOu1oAP5oFqgBr7`，tool execution consumed_by 为 `codex-call-0002`，subagent call model 均为 `gpt-5.5`。

- [x] 2.3 更新目标 session `expected.normalized.jsonc` 并补充 normalized 聚焦测试。
  - 验证：PASS — `docs/session-samples/codex/.../expected.normalized.jsonc` 去注释后与 `~/Downloads/normalized.json` 完全一致；新增 `test_codex_three_agent_sample_matches_recovered_call_graph`。

## 阶段 3：归因 payload

- [x] 3.1 调整 Codex source-unit accounting：request candidates 不伪造 token mass，cache read/write 只作为 accounting field。
  - 验证：PASS — Codex mapper 对 request candidates 输出 `token_status=unknown_mass`、`candidate_total_tokens=0`，fresh residual 保留 provider fresh input。

- [x] 3.2 补充 Codex attribution 聚焦测试，覆盖 unknown_mass/residual 与 response 非 reasoning 不精确拆分。
  - 验证：PASS — `tests/test_llm_attribution_codex.py` 断言 request unknown_mass、response reasoning exact_provider 与 non-reasoning unknown_mass。

## 阶段 4：验证

- [x] 4.1 运行 Codex 聚焦测试。
  - 验证：PASS — `python3 -m pytest tests/normalized/test_codex_adapter_snapshots.py tests/test_llm_attribution_codex.py tests/test_llm_attribution_bucket_normalization.py -q`，结果 `30 passed`。

- [x] 4.2 运行 OpenSpec、harness 和 required quality gates。
  - 验证：PASS — `python3 scripts/openspec/validate_layout.py && python3 scripts/openspec/validate_schema.py && python3 scripts/openspec/validate_active_change.py --change-id fix-codex-token-mass-recovery && python3 scripts/harness/validate_harness_structure.py`；`python3 scripts/quality/run_required_quality_gates.py --change-id fix-codex-token-mass-recovery`；补充全量 `python3 -m pytest tests -q`，结果 `3526 passed`。
