# Quality Gate 矩阵

仅当任务涉及路径分类、required gate 选择、Stop 门禁失败或新增质量目标时读取本文件。

## 真源

- target 列表真源：`scripts/quality/quality_targets.py`
- 路径分类真源：`scripts/claude_hooks/classify.py`
- 执行入口：`scripts/quality/run_quality_gate.py`
- Stop 汇总入口：`scripts/quality/run_required_quality_gates.py`
- 三档配置：`harness/quality/quality-tiers.yaml`

本文件只解释阅读路线，不复制完整矩阵，避免和脚本漂移。

## 质量门三档

质量门分为 quick、required、full 三档，对应不同场景和严格程度。

| 档位 | 用途 | 失败策略 | 运行方式 |
|---|---|---|---|
| **quick** | 本地开发快速反馈，只运行轻量 gate 子集 | triggered gate 必须 PASS；not triggered 不算 skipped | `--tier quick` |
| **required** | PR 合入和 Stop/handoff 前必须通过 | 0 skipped outcome；skipped 即 FAIL/BLOCKED | `--tier required`（默认） |
| **full** | 发布或大迁移收口前运行 | 0 skipped outcome；包含额外验证命令 | `--tier full` |

运行命令：

```bash
# quick 档：本地开发快速反馈
python3 scripts/quality/run_required_quality_gates.py --tier quick

# required 档：PR/Stop 门禁（默认，向后兼容）
python3 scripts/quality/run_required_quality_gates.py --tier required
python3 scripts/quality/run_required_quality_gates.py  # 默认即 required

# full 档：发布或大迁移收口
python3 scripts/quality/run_required_quality_gates.py --tier full
```

### quick 档说明

quick 档只运行 `QUICK_GATES` 中定义的轻量级 gate 子集，包括：

- `pythonCompile`、`bashSyntax`：语法检查
- `noTestSkips`、`noJavaTestSkips`：测试零跳过检查
- `noJavaSuppressWarnings`：Java 注解检查
- `languagePolicy`：语言策略检查
- `doctor`、`repoStructure`、`harnessStructure`：结构验证

quick 档通过各 target 的 baseline 过滤出属于 `QUICK_GATES` 的 gate，只运行被 changed_files 触发的 target 中的轻量 gate。

### not triggered 与 skipped 的语义区别

这是质量门系统最重要的语义规则之一：

| 概念 | 含义 | 是否算失败 |
|---|---|---|
| **not triggered** | gate 的触发模式未匹配 changed_files，该 gate 未被选中运行 | 不算失败，不影响结果 |
| **skipped** | gate 被选中运行，但测试框架报告了 skipped tests 或 gate 未完成完整验证 | required/full 档中即 FAIL/BLOCKED |

关键规则：

1. `changed_files` 只决定触发，不代表 skipped。未匹配任何触发模式的 gate 是 not triggered，不得在汇报中称为 skipped。
2. 一旦被 target 选中，gate 必须运行完整 baseline。
3. required/full 档中被选中的 gate 出现 skipped outcome 必须返回 FAIL/BLOCKED。
4. quick 档中 not triggered 的 gate 单独记录，不算 skipped，不影响退出码。

## 当前 target

| Target | 典型触发路径 | 主要 gate |
|---|---|---|
| `session-detail` | UI 模板、CSS、前端 JS | 模板契约、CSS 契约、浏览器布局、pytest |
| `python-standard` | 手动标准 Python 工具体系验证 | Ruff Formatter/Ruff、Pyright、interrogate/pydoclint、pytest-cov/Coverage.py、pip-audit/Bandit、Xenon、Vulture、Deptry |
| `hook-runtime` | hooks、agent 配置、质量脚本 | settings、bash syntax、python compile、policy、pytest、doctor、noTestSkips |
| `harness` | `harness/**`、`scripts/harness/**` | doctor、仓库结构、harness 结构、OpenSpec 布局、noTestSkips |
| `acceptance-contracts` | `docs/acceptance-contracts/**`、`tests/**` | 验收契约映射、pytest、noTestSkips |
| `index` | index 相关源码 | index integrity |
| `java-src` | `java/**/src/**/*.java` | Java 编译检查、中文注释校验、测试零跳过 |
| `java-build` | `build-logic/**`、`gradle/**`、`build.gradle.kts`、`settings.gradle.kts`、`gradle.properties` | Java 编译检查 |

`java-src` 包含 `java-build`（dominance）：当 java-src 触发时自动覆盖 java-build，避免重复运行 Gradle baseline。

## 修改规则

- 新增 target 时同步 `QUALITY_TARGETS`、`GATE_PATTERNS`、分类规则和测试。
- `python-standard` 是历史负债修复前的手动能力 target；不得在 Ruff、Pyright、docstring、coverage、audit、complexity、dead-code 和依赖声明问题全量清零前映射为自动 required gate。
- 改 agent、skill、hook 或 prompt 文件时，必须触发 `hook-runtime` 或 `harness`。
- 改测试或验收契约时，必须触发 `acceptance-contracts`。
- 改 UI 页面时，不得只跑静态检查；需要包含对应浏览器或交互 gate。
- `GATE_PATTERNS` 只表达触发映射。未命中的 gate 是 not triggered；不要在汇报中称为 skipped。
- 被 target 选中的 gate 必须运行完整 baseline。若测试框架输出 skipped tests，应视为 gate 未完成验证，而不是 PASS；selected / required gate 出现 skipped outcome 必须返回 `FAIL`/`BLOCKED`。
- 全量回归和发布回归不走 changed-files 裁剪；必须证明完整集合 `0 skipped`，任何 skipped tests 都必须先解释为 fixture/env 缺失并修复，或报告 `FAIL`/`BLOCKED`。
- 新增 pytest / Playwright skip API 由 `scripts/quality/check_no_test_skips.py` 的 `noTestSkips` gate 阻止；不得通过 allowlist 保留历史测试 skip。
