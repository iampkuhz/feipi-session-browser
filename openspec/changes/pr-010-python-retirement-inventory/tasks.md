# Tasks: PR-010 S7 Python Retirement Inventory

## Task List

| Order | ID | Kind | Title | Status |
|-------|------|------|-------|--------|
| 58 | PR-010 | PLAN | Python 产品运行代码与开发工具全量分类 | PASS |
| 59 | PR-020 | IMPLEMENT | 删除 Python Scan/Index/Normalized 产品运行代码 | pending |
| 60 | PR-030 | IMPLEMENT | 删除 Python Query/Web/CLI 产品运行代码 | pending |
| 61 | PR-040 | IMPLEMENT | 删除 Python 产品依赖、容器与发布链 | pending |
| 62 | PR-050 | IMPLEMENT | Shell、CI、Harness、Docs 与 Ownership 最终同步 | pending |
| 63 | PR-055 | OPTIMIZE | 最终仓库精简、Dead Code、依赖与复用优化 | pending |
| 64 | PR-060 | GATE | 零 Python 产品运行时与发行内容只读门禁 | pending |
| 65 | PR-070 | CLOSEOUT | 最终 Java 产品与仓库 Stage 收口 | pending |

## PR-010 Classification Summary

| Category | Count | Description |
|---|---:|---|
| DELETE | 88 | 已由 Java 全面接管的 Python 产品代码、容器、CI |
| DEV_TOOL | 101 | 开发质量工具、harness、CI、release 脚本 |
| FIXTURE_GENERATOR | 2 | 测试 fixture 生成脚本 |
| TEST_INFRASTRUCTURE | 181 | Python 测试文件 |
| NEEDS_DECISION | 101 | attribution/ 模块（LLM 费用归因） |
| PRODUCT_RUNTIME | 0 | 所有产品运行代码均已在 DELETE 或 NEEDS_DECISION |
| **Total** | **473** | |

## PR-010 Validation

- `./gradlew check`: BUILD SUCCESSFUL, 1729 tests, 0 failed
- `./scripts/session-browser.sh test`: 3709 passed, 1 failed (pre-existing, unrelated)
- Inventory SHA-256: `1bbf9ea0514a22d52ec97776a2d88130df3a1f04e98771f688ad6ebb3f4f57f`
- Checkpoint commit: `9686bfd7`
