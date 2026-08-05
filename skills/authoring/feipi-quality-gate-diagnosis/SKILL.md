---
name: feipi-quality-gate-diagnosis
disable-model-invocation: true
description: 用于 Gate、doctor 或显式质量检查未通过后的诊断和最小修复；功能开发前置设计不要使用。
---

# 质量门诊断

本 skill 为 Gate、doctor 和显式质量检查未通过后的诊断与最小修复提供固定流程。核心原则：先定位
Gate 和 Trigger，再区分 `BLOCKED`（检查结论阻断交付）与 `FAIL`（Gate 自身未完成），最后做最小修复。

## 何时使用

- 增量或全量 Gate 返回 `BLOCKED`/`FAIL`（如 `agent.skill-registry`、OpenSpec 或产品 Gate）。
- Doctor 脚本（`scripts/harness/doctor.sh`）失败。
- Java gates（编译、测试、PMD）失败。
- UI gates（静态检查、JS action handler 检查）失败。
- Agent policy、skill registry 或 OpenSpec 结构检查失败。
- 任何 Gate 返回非零 exit code。

## 不要何时使用

- 功能开发前置设计 → 使用对应功能 skill（如 `feipi-java-feature-dev`、`feipi-session-detail-ui-dev`）。
- OpenSpec 编排 → 使用 `feipi-openspec-orchestrate-change`。
- 纯 session 数据查看或分析 → 不要使用本 skill。
- 功能实现过程中的中间调试 → 直接修复代码，不需要走完整诊断流程。
- 非 gate 失败的普通 bug 修复。

## 输入最小化

只读取以下必要片段：

1. 失败 gate 的命令和完整 exit code。
2. 失败 gate 的脚本源码 — 只读触发失败的脚本，不读无关实现。
3. 失败输出中具体的错误信息、Gate Trigger 和 mode。
4. 与失败直接相关的文件片段。

Gate 状态、模块边界与 rerun 入口以 `scripts/gates/README.md` 为导航；当前 Gate/Target 名称从
`scripts/gates/catalog.py` 或 `python3 scripts/gates/cli.py --dry-run` 派生，不读取文档静态矩阵。

不要全仓库扫描。不要预读无关 gate 脚本或实现文件。不要读取真实 session 数据。

## 执行步骤

1. **记录失败命令和完整 exit code**：复制触发失败的完整命令，记录 exit code（不是 0 的值）。不要截断或概括输出。
2. **定位 Gate 和 mode**：从失败输出中提取 Gate 名称、`incremental/full` 与 changed files；Target 只在显式 selector 调用中出现。
3. **读取 gate 脚本，不读无关实现**：只读触发失败的 gate 脚本源码，理解它的检查逻辑和断言条件。不要读取与当前失败无关的其他 gate 脚本或产品代码。
4. **找到失败文件和具体断言**：从 gate 输出中定位具体失败的文件路径和断言信息（如 "缺少必需文件"、"symlink 目标不存在"、"required skill 目录不存在"）。
5. **判断失败类别**：将失败归类为以下五类之一：
   - **环境缺失**：Python 不可用、依赖未安装、脚本文件不存在。
   - **Fixture 缺失**：测试 fixture、mock 数据、示例文件不存在。
   - **代码失败**：产品代码不满足 gate 断言（如缺少 SKILL.md、registry 条目不匹配）。
   - **配置漂移**：配置文件与实际状态不一致（如 manifest 引用不存在的 skill、registry 缺少新增条目）。
   - **Gate 本身 bug**：gate 脚本逻辑错误导致误报。
6. **环境缺失 → FAIL**：如果是环境缺失（如 Python 不可用、必要工具未安装），报告带 reason code 的 `FAIL`，不伪造 PASS。不要尝试安装依赖或修改环境。
7. **Fixture 缺失 → 补最小 fixture**：如果是 fixture 缺失，补最小必要的 fixture 文件或 mock 数据，使其满足 gate 断言。不要补多余的 fixture。
8. **代码失败 → 最小修复**：如果是代码失败，做最小修复使其满足 gate 断言。不要重构、不要扩大修改范围、不要修改与当前 gate 失败无关的代码。
9. **Gate bug → 补 gate 自测**：如果是 gate 本身逻辑错误，修复 gate 脚本并补充对应的自测用例，确保修复后不误报也不漏报。
10. **重跑原 Gate，再跑增量交付检查**：修复后先精确重跑原 Gate，确认 PASS；再运行 `--mode incremental` 确认没有引入回归。
11. **输出 PASS/FAIL/BLOCKED**：输出最终状态，不允许把 skipped、未运行、环境受限描述为 PASS。如果有任何 gate 未运行，必须写明原因。

## 文件边界

- Gate 唯一公开入口：`scripts/gates/cli.py`；内部 catalog/planner/executor/receipt/report 不直接运行。
- 领域检查器：`scripts/checks/<domain>/*.py`；只在定位单个失败时运行报告给出的精确 rerun 命令。
- Harness 体检：`scripts/harness/doctor.sh`。
- Registry 配置：`harness/skill-registry.yaml`。
- Harness 配置：`harness/manifest.yaml` 与 `harness/agent-policy.manifest.yaml`。
- Agent 入口：`.claude/agents/*.md`、`.codex/agents/*.toml`。
- Skill 源目录：`skills/authoring/<skill-name>/`。
- Skill 入口：`.agents/skills/<skill-name>`、`.claude/skills/<skill-name>`、`.codex/skills/<skill-name>`。

不要跨边界修改产品代码（Java、Python 产品逻辑）。不要修改与 gate 失败无关的配置文件。不要重新引入平台 Hook、Session Registry、writer lease 或自动 Git mutation。

## 验证门禁

以下命令用于分层诊断；被选 Gate 未完整执行时必须返回 FAIL：

- 触发失败的 gate — 必须重跑并 PASS。
- `python3 -m scripts.checks agent.skill-registry` — registry 完整性。
- `bash scripts/harness/doctor.sh` — 全量环境体检。
- `python3 scripts/gates/cli.py --mode incremental` — 普通提交和交接的增量检查。

选择策略：

- 单个 gate 失败 → 修复后重跑该 gate + `doctor.sh`。
- Registry/manifest 相关 → 追加 `agent.skill-registry` 与 minimal harness 结构检查。
- 收口前 → 运行 `python3 scripts/gates/cli.py --mode incremental`。

若诊断结果需要新增、修改或删除 Gate，退出本 skill 的单点修复模式，按
`scripts/gates/README.md` 的 catalog + 对应 check + contract 唯一流程执行；不得新增 runner 或文档矩阵。

## 输出格式

使用 `templates/report.md` 模板。变更摘要必须包含：

- 失败 gate 名称和 exit code。
- 失败类别（环境缺失/fixture 缺失/代码失败/配置漂移/gate bug）。
- 最小修复内容。
- 重跑结果（PASS/FAIL/BLOCKED）。
- 增量交付检查的运行结果。
- 未运行的 gate 及原因。
- 后续风险或 TODO。
