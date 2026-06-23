# Feipi Session Browser — Agent 工程规则

本文件仅用于非平凡开发、OpenSpec、harness、质量门、hooks、agent 配置或仓库规则改造；普通定位、单文件小改、简单文档修改不扩展上下文。

## 首要护栏

- 默认使用简体中文；规约、规格、提示词、模板、流程文档和 UI 文案默认中文。
- 代码标识符、命令、路径、API 保持英文。
- 先搜索定位，再只读必要片段；不要加载无关 skill、长文档或历史材料。
- 修改最小化；不覆盖用户改动，不纳入缓存、运行数据、真实 session、密钥、token 或个人配置。
- `subagent` 默认积极触发：长任务、并行探索、独立验证、日志隔离或清晰分工时主动委派；简单单点改动、缺少 scope 或写冲突时不委派。
- 调用 `subagent` 前给最小 handoff、allowed scope、forbidden scope、预期输出和验证命令；实现型任务拆成不重叠写范围。
- 共用 hook、subagent、skill、质量门规则沉淀到 `skills/`、`harness/` 或 `scripts/harness/`；`.claude/`、`.codex/`、`.qoder/`、`.agents/` 只保留入口或链接。

## 任务分流

以下属于非平凡变更：

- 新增或改变产品行为；
- 改动 OpenSpec、harness、质量门、hooks、agent 配置；
- 调整目录职责、开发流程、验证流程；
- 跨多个模块的结构性改造；
- 影响长期维护方式的文档或脚本变更。

非平凡变更先确认 `openspec/changes/<change-id>/`；没有时先补齐任务再实现。`openspec/specs/` 是长期真相，`openspec/changes/` 是待实施变更；不要绕过 OpenSpec 大改受保护路径。

## 受保护路径

修改以下路径必须目标明确、范围最小并检查 diff：

- `.claude/`、`.codex/`、`.qoder/`、`.agents/`、`skills/`
- `openspec/`、`harness/`、`scripts/`
- `src/session_browser/`、`tests/`
- `AGENTS.md`、`CLAUDE.md`

不提交 `.gitignore` 忽略文件；`openspec/changes/*` 默认不得 `git add -f`，除非用户明确要求。不维护“废弃”信息；不用的文档、契约用例和测试直接删除。

## 验证原则

修改后必须让本次触发的 required quality gates 全部通过，才能描述完成。失败项即使看似非当前 agent 引入，也必须修复或报告阻断；不得把失败、未运行、跳过或“非本人改动”描述为通过。

完整基线使用 `scripts/quality/run_required_quality_gates.py`。

触发与 skip 语义：

- changed-files / quality target 映射只决定“是否触发”。未被映射选中的测试或 gate 是 not triggered，不得写成 skipped。
- 一旦人工指定、映射选中、required gate、full regression 或 release regression 确认某个测试/gate 必须运行，运行期间出现 skipped outcome 不得算 PASS；必须补齐 fixture/env、从触发映射中移除，或报告 `FAIL`/`BLOCKED`。
- 发布回归、full regression、required quality gate 不允许用 skip 替代验证；必须证明选中集合是 `0 skipped`，否则返回 `FAIL`/`BLOCKED` 并说明缺失条件。
- 新增测试 skip API 由 `scripts/quality/check_no_test_skips.py` 的 `noTestSkips` gate 阻止；不得新增 `pytest.skip`、`pytest.mark.skip`、`pytest.mark.skipif`、Playwright `test.skip()`、`test.describe.skip` 或 `test.fixme`。

选择规则：

- 改 `skills/`、`harness/`、`openspec/`、agent 配置、`scripts/`、`AGENTS.md` 或 `CLAUDE.md`：优先运行 `bash scripts/harness/doctor.sh`。
- 改产品代码或测试：运行 `./scripts/session-browser.sh test`。
- 改 UI 模板、CSS、前端 JS：运行对应 UI 质量门。
- 改 `java/**/src/**/*.java`：触发 `java-src` target（包含 `java-build` dominance）。
- 改 `build-logic/**`、`gradle/**`、`build.gradle.kts`、`settings.gradle.kts`、`gradle.properties`：触发 `java-build` target。
- Stop / handoff 前运行 `scripts/quality/run_required_quality_gates.py` 或等价 required baseline；该 baseline 不得按 changed-files 裁剪 target 内部 gate。
- Java 侧规约（Lombok 允许清单、枚举精简、`@SuppressWarnings` 禁令等）见 `openspec/specs/java-code-conciseness/spec.md`，仅在涉及 Java 源码改造时加载。
