# 验收契约映射框架 — 最终证据报告

> 生成时间：2026-05-27
> 变更 ID：acceptance-contract-mapping

## 改造摘要

本次改造在 `feipi-session-browser` 仓库中建立了完整的"验收契约映射框架"，包括：

1. **验收契约文档体系**：在 `docs/acceptance/` 下创建了 13 个功能域契约文档，覆盖数据源、索引、presenter、路由 API、各 UI 页面、交互和 hook harness。
2. **测试 ID 绑定**：为现有 Playwright 测试标题添加了契约 ID，为 pytest 测试添加了 `@pytest.mark.contract_case` marker。
3. **契约映射校验脚本**：新建 `validate_test_contract_mapping.py`，自动校验 md 契约用例与代码测试的一致性。
4. **映射脚本测试**：新建 31 个单元测试覆盖 8 个校验场景。
5. **质量门禁接入**：新增 `testContractMapping` 质量 target，集成到既有 `run_quality_gate.py`。

## 新增/修改文件

### 新增文件（20 个）

| 文件 | 说明 |
|---|---|
| `docs/acceptance/README.md` | 验收契约体系说明 |
| `docs/acceptance/ACCEPTANCE_CHECK_MATRIX.md` | 总检查矩阵 |
| `docs/acceptance/TEST_CONTRACT_ID_RULES.md` | 测试 ID 命名规则 |
| `docs/acceptance/features/DATA_SOURCES.md` | 数据源契约（16 用例） |
| `docs/acceptance/features/DATA_INDEX.md` | 数据索引契约（13 用例） |
| `docs/acceptance/features/DATA_PRESENTERS.md` | Presenter 契约（14 用例） |
| `docs/acceptance/features/ROUTES_AND_API.md` | 路由 API 契约（13 用例） |
| `docs/acceptance/features/UI_DASHBOARD.md` | Dashboard 契约（8 用例） |
| `docs/acceptance/features/UI_SESSIONS_LIST.md` | 会话列表契约（17 用例） |
| `docs/acceptance/features/UI_SESSION_DETAIL.md` | 会话详情契约（30 用例） |
| `docs/acceptance/features/UI_PROJECTS.md` | 项目页契约（10 用例） |
| `docs/acceptance/features/UI_AGENTS.md` | Agent 页契约（8 用例） |
| `docs/acceptance/features/UI_GLOSSARY.md` | 术语表契约（3 用例） |
| `docs/acceptance/features/UI_GLOBAL_VISUAL.md` | 全局视觉契约（15 用例） |
| `docs/acceptance/features/UI_INTERACTIONS.md` | 交互契约（12 用例） |
| `docs/acceptance/features/HOOK_HARNESS.md` | Hook/Harness 契约（15 用例） |
| `docs/acceptance/generated/TEST_CONTRACT_COVERAGE.md` | 覆盖率报告（自动生成） |
| `docs/acceptance/generated/ORPHAN_TESTS.md` | 孤立测试报告（自动生成） |
| `scripts/quality/validate_test_contract_mapping.py` | 契约映射校验脚本 |
| `tests/quality/test_validate_test_contract_mapping.py` | 映射脚本单元测试（31 用例） |

### 修改文件（约 139 个）

- `pyproject.toml` — 注册 `contract_case` marker
- `scripts/quality/quality_targets.py` — 新增 `testContractMapping` target
- `scripts/quality/run_quality_gate.py` — 接入 `testContractMapping` gate
- `tests/playwright/*.spec.js` — 6 个文件，添加契约 ID（42 个测试）
- `tests/playwright/*.spec.ts` — 1 个文件，添加契约 ID
- `tests/**/*.py` — 约 130 个测试文件，添加 `@pytest.mark.contract_case` marker

## 契约用例数量

| 优先级 | 数量 |
|---|---:|
| P0 | 96 |
| P1 | 62 |
| P2 | 16 |
| P3 | 0 |
| **总计** | **174** |

## 代码绑定数量

| 类型 | 数量 |
|---|---:|
| pytest marker 绑定 | 145 |
| Playwright 标题绑定 | 21 |
| **代码绑定总计** | **166** |

绑定覆盖率：**95.4%**（166/174）

未绑定的 8 个用例均为 P2 优先级（manual 检查或待补充 E2E 交互）。

## 检查命令结果

| 命令 | 结果 |
|---|---|
| `python3 scripts/quality/validate_test_contract_mapping.py` | **PASS** |
| `python3 -m compileall -q src scripts tests` | **PASS** |
| `pytest -q tests/quality/test_validate_test_contract_mapping.py` | **PASS**（31 passed） |
| `pytest -q` | **3255 passed, 13 failed**（13 个预存在失败） |
| `python3 scripts/quality/run_quality_gate.py --target python-src` | **PASS** |
| `python3 scripts/quality/run_quality_gate.py --target session-detail` | **PASS** |
| `python3 scripts/quality/run_quality_gate.py --target testContractMapping` | **PASS** |
| `bash scripts/harness/doctor.sh` | **PASS** |

### 预存在失败说明

13 个 pytest 失败在改动前已存在（通过 `git stash` 验证），与本次契约改造无关：

- `tests/rendering/test_copy_action_contract.py`（3 个）：copy action 模板契约
- `tests/pages/test_project_detail_page.py`（3 个）：项目详情页结构
- `tests/pages/test_projects_page.py`（2 个）：项目列表页操作
- `tests/pages/test_timeline_expandability.py`（1 个）：时间线事件委托
- `tests/sessions_list/test_sessions_list.py`（1 个）：sessions JS import
- `tests/ui/test_ui_contract_static.py`（3 个）：UI 静态契约

## 未完成项

| 项 | 说明 |
|---|---|
| 8 个 P2 用例未绑定代码 | 均为 manual 检查或待补充的 E2E 交互（Projects/Agents/Glossary 页面交互空白） |
| 7 个 Playwright 动态循环测试 | 无静态契约 ID，暂不标记 |
| Playwright 全量 E2E | 需要 Playwright 运行环境，未在 CI 中执行 `npx playwright test` |

## 风险说明

1. **Playwright snapshot 未更新**：本次改造严格遵守不执行 `--update-snapshots` 的原则。现有快照基线保持不变。
2. **import pytest 批量修复**：任务 4 的 subagent 在 130+ 个测试文件中添加了 `import pytest`，过程中出现了若干次 docstring 损坏，已通过多轮修复解决。最终 `pytest -q` 通过 3255 个测试（13 个预存在失败）。
3. **环境依赖**：Playwright 全量 E2E 测试需要 `node_modules` 和 Playwright 浏览器环境，本次改造未验证此路径。
4. **contract_case marker 语义**：新增的 `contract_case` marker 仅用于契约映射校验，不影响测试逻辑和断言行为。

## 后续建议

1. 为 Projects/Agents/Glossary 页面补充 E2E 交互测试，消除 8 个未绑定 P2 用例
2. 将 `validate_test_contract_mapping.py` 加入 CI 预检查步骤
3. 考虑为 snapshot 测试建立定期回归流程，确保视觉基线不漂移
4. 对 13 个预存在失败的测试进行独立修复
5. 新增测试文件时同步更新 `docs/acceptance/features/*.md` 契约用例
