# Quality Gate 矩阵

仅当任务涉及路径分类、required gate 选择、Stop 门禁失败或新增质量目标时读取本文件。

## 真源

- target 列表真源：`scripts/quality/quality_targets.py`
- 路径分类真源：`scripts/claude_hooks/classify.py`
- 执行入口：`scripts/quality/run_quality_gate.py`
- Stop 汇总入口：`scripts/quality/run_required_quality_gates.py`

本文件只解释阅读路线，不复制完整矩阵，避免和脚本漂移。

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
