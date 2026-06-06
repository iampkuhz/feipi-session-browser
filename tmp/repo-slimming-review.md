# 仓库瘦身审查报告

生成时间：2026-06-06

## 总览

- 规模：107 个已跟踪文件变更，约 393 行新增、6567 行删除。
- 主方向：删除历史 OpenSpec change、人工验收矩阵、harness 旧手册、fixture/ hook 说明文档；保留并重写 `docs/ui/` 为页面功能要求集合。
- 代码侧：移除依赖已删文档的质量目标和脚本；清理 CSS 历史迁移注释、Dashboard 旧 hero 样式、空兼容 alias。
- 保留：`README.md`、`AGENTS.md`、`CLAUDE.md`、`docs/ui/`、`openspec/specs/`、OpenSpec 模板、执行脚本和测试代码中的当前行为测试。

## 新增变更任务

- `openspec/changes/slim-repository-docs/proposal.md`：本次瘦身目标，包含保留 `docs/ui/` 的要求。
- `openspec/changes/slim-repository-docs/design.md`：删除、保留和收敛策略。
- `openspec/changes/slim-repository-docs/tasks.md`：执行任务清单。
- `openspec/changes/slim-repository-docs/specs/repo-slimming/spec.md`：当前状态文档规格增量。

说明：`openspec/changes/*` 在本仓库被忽略，上述文件用于本地审查。

## 删除的文档

- `harness/context/*.md`：删除渐进式上下文包。
- `harness/governance/quality-gate-repair.md`：删除旧治理手册。
- `harness/quality/*.md`：删除质量矩阵、诊断、CSS ownership、布局合同等 5 份手册。
- `harness/workflow/*.md`：删除 change lifecycle 和 subagent execution 手册。
- `openspec/changes/*`：删除已跟踪历史 change 文档，仅保留当前瘦身 change 和 archive 占位。
- `tests/acceptance/**/*.md`：删除人工验收矩阵、功能域表、逐页行为手册。
- `tests/hooks/README.md`：删除 hook 测试说明。
- `tests/fixtures/session_hifi_fixture/README.md`、`tests/fixtures/session_hifi_long_fixture/README.md`：删除 fixture 说明。

## 保留并重写的 UI 要求文档

- `docs/ui/README.md`：新增 `docs/ui/` 入口，说明页面功能要求维护方式。
- `docs/ui/contracts/01-global-ui-contract.md`：重写为全局 UI 要求。
- `docs/ui/contracts/02-component-contracts.md`：重写为组件要求。
- `docs/ui/contracts/03-page-contracts.md`：重写为页面功能总入口和逐页要求。
- `docs/ui/contracts/05-button-icon-behavior.md`：重写为按钮、图标、tooltip、modal 行为要求。
- `docs/ui/contracts/06-validation-contract.md`：重写为验证入口和文档对齐要求。
- `docs/ui/contracts/07-data-contract.md`：重写为页面数据展示要求。
- `docs/ui/contracts/css-load-order.md`：重写为 CSS 加载顺序和所有权要求。
- `docs/ui/contracts/shell-state-contract.md`：重写为 Shell 状态要求。
- `docs/ui/design/sessions_list_component_system.md`：重写为 Sessions 列表组件要求。
- `docs/ui/design/sessions_list_interaction_contract.md`：重写为 Sessions 列表交互要求。

## 修改的文件

- `.claude/skills/change/reference/workflow.md`：改为引用 `AGENTS.md` 和当前 change tasks。
- `.claude/skills/change/reference/subagent-contract.md`：删除已删 workflow 手册引用。
- `harness/README.md`：重写为 21 行当前入口，只保留 manifest、doctor、quality gate。
- `harness/manifest.yaml`：docs 列表收敛为 `harness/README.md`。
- `openspec/README.md`：去掉历史归档叙述，保留当前结构。
- `openspec/specs/page-function-standard/spec.md`：改为以 `docs/ui/` 页面功能要求为真源。
- `scripts/harness/validate_harness_structure.py`：不再要求已删 harness 文档目录。
- `scripts/openspec/validate_schema.py`：不再要求已删 harness 文档目录。
- `scripts/harness/validate_ui_reference_links.py`：改为跳过仓库内 UI 参考文档检查。
- `scripts/quality/quality_targets.py`、`scripts/quality/run_quality_gate.py`：移除 `testContractMapping` 质量目标。
- `scripts/quality/repo_slimming_contract_check.py`：仓库扫描排除自身测试样本，避免误报。
- `scripts/quality/check_css_ownership.py`：去掉对已删 Markdown 真源的引用。
- `scripts/qa/ui/check_ui_contracts.py`：重写为当前静态 UI 检查，不再依赖旧合同和旧 `style.css`。
- `scripts/qa/ui/check_sessions_list_html.py`：删除已删 acceptance 行为手册引用。
- `src/session_browser/web/templates/base.html`：删除 CSS ownership 文档引用。
- `src/session_browser/web/static/css/dashboard.css`：删除 Dashboard 旧 `.hero*` 样式和相关响应式残留。
- `src/session_browser/web/static/css/projects.css`：删除旧 tokenbar tooltip 禁用兜底。
- `src/session_browser/web/static/css/session-detail/04-timeline.css`：删除空兼容 alias 和 fallback 注释。
- `src/session_browser/web/static/css/session-detail/05-round-detail.css`、`sessions-list.css`、`ui-primitives/*.css`：批量删除 `Migrated from style.css` / `Originally at style.css` 历史注释。

## 删除的代码/测试工具

- `scripts/quality/validate_test_contract_mapping.py`：删除依赖 `tests/acceptance/features/*.md` 的死工具。
- `tests/quality/test_validate_test_contract_mapping.py`：删除对应单测。

## 验证结果

- `bash scripts/harness/doctor.sh`：通过；仅提示本地 `.claude/settings.local.json` 存在，属 gitignored 个人配置告警。
- `python3 scripts/harness/validate_harness_structure.py`：通过。
- `python3 scripts/harness/validate_openspec_layout.py`：通过。
- `python3 scripts/quality/repo_slimming_contract_check.py`：通过。
- `python3 scripts/qa/ui/check_ui_contracts.py`：通过。
- `python3 scripts/quality/check_css_ownership.py`：通过；保留既有 WARN。
- `python3 -m compileall -q scripts/quality scripts/harness scripts/openspec scripts/qa src`：通过。
- `pytest -q tests/quality/test_repo_slimming_contract.py tests/quality/test_quality_gate_runner.py tests/quality/test_run_required_quality_gates.py`：70 passed。

## 注意

- 未触碰未跟踪目录 `.refactor-artifacts/`。
- 本次没有删除 fixture 数据本体，只删除 fixture README。
- 本次没有提交 git。
