# Design: Eliminate historical test skips

## Current state

初始盘点命令：

```bash
rg -n "pytest\\.skip|pytest\\.mark\\.skip|pytest\\.mark\\.skipif|test\\.skip\\(|\\bskipped\\b|\\bskipif\\b" tests scripts playwright.config.js package.json
```

发现的测试 skip 来源包括：

- 静态 pytest skip marker：旧 UI/契约漂移、fixture 字段不足、删除后的 tab/API 用例。
- runtime pytest skip：缺本地 `SB_TEST_DB`、本地索引不存在、模板/CSS/JS 文件不存在、fixture 数据为空、payload/button/row 缺失。
- Playwright skip：`PW_SESSION_URL` 缺失、没有 session 行、fixture 中缺少 dashboard chart scope。
- optional dependency 缺失：`bs4` 缺失时 module-level skip。
- 非测试语义：indexer / JSONL reader 中的 `skipped` 业务计数、quality runner 对 Playwright skipped output 的检测、UI 截图报告中的缺参考图计数。

当前 `./scripts/session-browser.sh test -q` 结果为 `3429 passed, 62 skipped`。

## Proposed approach

### 1. 测试清理

- 删除已被产品行为取代的历史契约 skip（例如 removed metrics/payloads tab、removed apply button、旧 placeholder 文案）。
- 对仍有价值的测试改写为当前契约，或补 fixture 数据/构造 deterministic HTML/DB。
- 将文件存在性和 fixture 数据前置条件从 skip 改为明确 `assert`/`pytest.fail`，使缺 fixture 是失败而不是通过。
- 将依赖真实本地索引的 fixture fallback 到仓库内 HIFI deterministic fixture；`SB_TEST_DB` 缺失时使用临时 fixture SQLite/服务端。
- 引入 `beautifulsoup4` 到 dev requirements，避免 `bs4` optional skip；如依赖已存在则保持。
- Playwright 中缺 `PW_SESSION_URL` 或缺 DOM 数据时改为明确断言；root config 通过 fixture server/webServer 或现有 baseURL 支持直接运行。

### 2. 静态质量门

新增 `scripts/quality/check_no_test_skips.py`：

- 扫描 `tests/**/*.py` 中的 `pytest.skip(`、`pytest.mark.skip`、`pytest.mark.skipif`。
- 扫描 `tests/playwright/**/*.{js,ts}` 中的 `test.skip(`、`test.describe.skip`、`test.fixme`。
- 输出具体文件行并非零退出。
- 不扫描业务 `skipped` 字段；allowlist 仅限非测试语义且默认为空。

将 gate 接入 `hook-runtime`、`harness`、`acceptance-contracts`，并在 focused quality tests 中覆盖命令映射与失败输出。

### 3. runtime 防护

- 在 `tests/conftest.py` 注册 pytest hooks：记录任何 call/setup/teardown 阶段的 skipped report，在 session finish 时将 exit status 置为失败。
- xdist worker 中只记录，controller 汇总 skipped reports；若汇总不可用，单进程也可靠失败。
- Playwright 使用 `tests/playwright/no-skip-reporter.js`，统计 `testInfo.status === 'skipped'` 的结果，在 `onEnd` 返回非零 status。
- `playwright.config.js` 默认启用该 reporter，直接 `npx playwright test` 无法绕过。

## Risks

- 删除历史 skip 会减少过时断言数量；通过当前契约测试和 no-skip gate 弥补。
- 直接 `npx playwright test` 需要可用 fixture server；若当前页面契约仍失败，应修实现/测试或报告 `FAIL/BLOCKED`，不能改回 skip。
- xdist 下 pytest hook 汇总需要验证，避免 worker skipped 被 controller 漏掉。

## Rollback

回滚测试清理和 no-skip gate/reporter即可恢复旧行为，但会重新允许 skipped tests 作为 PASS，不建议回滚。

## Validation

见 `tasks.md`。
