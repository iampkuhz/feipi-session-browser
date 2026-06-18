# Proposal: Eliminate historical test skips

## Problem

仓库已经明确 not triggered 与 skipped after trigger 的区别，但历史测试仍通过 `pytest.skip`、`pytest.mark.skip`、`pytest.mark.skipif` 和 Playwright `test.skip()` 把缺 fixture、旧契约或缺环境包装成通过。当前 `./scripts/session-browser.sh test -q` 仍报告 `62 skipped`，直接 `npx playwright test` 也会因 `test.skip()` 在缺 fixture 时成功结束，发布/全量回归无法证明测试集合完整运行。

## Scope

- 清理测试中的 pytest 静态 skip marker、runtime `pytest.skip(...)` 和 Playwright `test.skip(...)`。
- 把历史 skip 用例删除、改写为当前契约，或补 deterministic fixture / 明确断言。
- 新增静态质量门，禁止后续新增测试 skip / fixme。
- 在 pytest runtime 层把 skipped outcome 转成失败，防止条件 skip 绕过静态扫描。
- 在 Playwright root config 中增加 no-skip reporter，保证直接 `npx playwright test` 出现 skipped tests 时失败。
- 将 no-skip gate 纳入 required quality targets，并补充 focused tests。
- 更新仓库规则、quality 文档和长期 OpenSpec，明确 full/release regression 必须 `0 skipped`。

## Non-goals

- 不读取或依赖真实 session 大文件。
- 不把业务字段（如 indexer 的 `skipped` 计数、JSONL diagnostics 的 skipped events）重命名。
- 不用环境变量关闭测试集合，也不裁剪 full/release regression 来规避失败。
- 不自动提交或强制 add `openspec/changes/*`。

## User impact

全量 pytest、Playwright 和 required quality gates 将更严格：只要某个被选中或人工运行的测试产生 skipped outcome，就会失败并要求补 fixture/env 或修正测试契约。changed-files 映射没有命中的 gate 仍是 not triggered，不等于测试 skip。

## Validation strategy

- OpenSpec / harness validators。
- `python3 scripts/quality/check_no_test_skips.py`。
- Focused quality runner tests。
- `./scripts/session-browser.sh test -q`，必须 `0 skipped`。
- `npx playwright test --workers=8`，必须 `0 skipped`。
- `python3 scripts/quality/run_required_quality_gates.py --change-id eliminate-historical-test-skips --include-session-detail --changed-files <current diff>`。
