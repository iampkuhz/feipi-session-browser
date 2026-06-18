# Tasks: Eliminate historical test skips

Walk these tasks sequentially. Mark each checkbox with validation evidence when done.

## Phase 1: Inventory and plan

- [x] 1.1 盘点并分类 pytest / Playwright / 非测试语义 skip 来源。
  - Validation: 已运行 `rg -n "pytest\\.skip|pytest\\.mark\\.skip|pytest\\.mark\\.skipif|test\\.skip\\(|\\bskipped\\b|\\bskipif\\b" tests scripts playwright.config.js package.json`，确认静态 pytest marker、runtime pytest skip、Playwright skip、fixture/env 缺失 skip 与业务 `skipped` 计数的边界。

- [x] 1.2 写入 proposal、design、tasks 和 spec delta。
  - Validation: 已写入 `proposal.md`、`design.md`、`tasks.md` 和 `specs/spec.md`。

- [x] 1.3 运行 OpenSpec / harness 规划验证。
  - Validation: `python3 scripts/openspec/validate_layout.py`、`python3 scripts/openspec/validate_schema.py`、`python3 scripts/openspec/validate_active_change.py --change-id eliminate-historical-test-skips`、`python3 scripts/harness/validate_harness_structure.py` 通过。

## Phase 2: Remove historical skips

- [x] 2.1 删除或改写静态 pytest skip marker 用例。
  - Validation: `rg -n "pytest\\.skip|pytest\\.mark\\.skip|pytest\\.mark\\.skipif" tests scripts playwright.config.js package.json || true` 无测试 skip API 命中。

- [x] 2.2 将 runtime pytest skip 改为 deterministic fixture、明确断言或失败。
  - Validation: `local_test_server` / `live_server_url` 默认落到 deterministic fixture；`./scripts/session-browser.sh test -q` 通过且无 skipped 汇总。

- [x] 2.3 删除 Playwright `test.skip()`，改为 fixture URL 或明确断言。
  - Validation: `rg -n "test\\.skip\\(|test\\.describe\\.skip|test\\.fixme" tests/playwright playwright.config.js package.json || true` 无命中；Playwright config 默认启动 fixture server。

## Phase 3: Enforcement gates

- [x] 3.1 新增 `scripts/quality/check_no_test_skips.py` 并补测试。
  - Validation: `python3 scripts/quality/check_no_test_skips.py` PASS；`./scripts/session-browser.sh test -q tests/quality/test_no_test_skips_gate.py tests/quality/test_quality_gate_runner.py tests/quality/test_run_required_quality_gates.py` PASS。

- [x] 3.2 将 no-skip gate 纳入 required quality targets。
  - Validation: `tests/quality/test_quality_gate_runner.py` 覆盖 `session-detail`、`hook-runtime`、`harness`、`acceptance-contracts` 中的 `noTestSkips` gate 与命令映射。

- [x] 3.3 在 pytest runtime 层禁止 skipped outcome。
  - Validation: `tests/quality/test_no_test_skips_gate.py::test_pytest_runtime_skip_enforcement_fails_session` 覆盖 skipped report 会将 pytest session 标为 failed。

- [x] 3.4 在 Playwright runtime 层禁止 skipped outcome。
  - Validation: `tests/playwright/no-skip-reporter.js` 已接入 `playwright.config.js`；`tests/quality/test_no_test_skips_gate.py` 覆盖 reporter 遇到 skipped result 返回 failed。

## Phase 4: Policy docs

- [x] 4.1 更新 `AGENTS.md`、quality 文档和长期 OpenSpec。
  - Validation: 子代理 `docs-policy-no-test-skips` PASS；`rg -n "not triggered|skipped|0 skipped|noTestSkips|check_no_test_skips" AGENTS.md harness/quality/deterministic-quality-gate.md harness/quality/quality-gate-matrix.md openspec/specs/agent-harness/spec.md` 覆盖必需语义。

## Phase 5: Validation

- [x] 5.1 运行静态 no-skip gate。
  - Validation: `python3 scripts/quality/check_no_test_skips.py` PASS，Findings: 0。

- [x] 5.2 运行 focused quality runner tests。
  - Validation: `./scripts/session-browser.sh test -q tests/quality/test_no_test_skips_gate.py tests/quality/test_quality_gate_runner.py tests/quality/test_run_required_quality_gates.py` PASS，48 passed。

- [x] 5.3 运行全量 pytest，确认 `0 skipped`。
  - Validation: `./scripts/session-browser.sh test -q` PASS，`3492 passed in 46.04s`，无 skipped 汇总。

- [x] 5.4 运行全量 Playwright，确认 `0 skipped`。
  - Validation: `npx playwright test --workers=8` PASS，`87 passed (22.6s)`，无 skipped 汇总；`tests/playwright/session-detail.spec.js` 与 `tests/playwright/sessions-list.spec.js` 中历史 skip/早退等待逻辑已改为 deterministic fixture/DOM 断言。

- [x] 5.5 运行 required quality gates 并收口。
  - Validation: `python3 scripts/quality/run_required_quality_gates.py --change-id eliminate-historical-test-skips --include-session-detail --changed-files '<current changed files>'` PASS；required targets `acceptance-contracts`、`harness`、`hook-runtime`、`python-src`、`session-detail` 全部 PASS，且 no-skip gate 均为 PASS。
