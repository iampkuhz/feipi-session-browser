# PR-010: Python 产品运行代码与开发工具全量分类

## Metadata

```yaml
id: PR-010
stage: S7
kind: PLAN
status: completed
```

## Goal

逐 Python 文件/依赖/工作流分类 PRODUCT_RUNTIME、DEV_TOOL、FIXTURE_GENERATOR、DELETE、NEEDS_DECISION。

## Inventory Summary

| Category | Count | Description |
|---|---:|---|
| DELETE | 88 | 已由 Java 全面接管的 Python 产品代码、容器、CI |
| DEV_TOOL | 101 | 开发质量工具、harness、CI、release 脚本 |
| FIXTURE_GENERATOR | 2 | 测试 fixture 生成脚本 |
| TEST_INFRASTRUCTURE | 181 | Python 测试文件 |
| NEEDS_DECISION | 101 | attribution/ 模块（LLM 费用归因） |
| PRODUCT_RUNTIME | 0 | 所有产品运行代码均已在 DELETE 或 NEEDS_DECISION |

## Key Findings

- 84 个 src/session_browser Python 文件分为 7 个模块：domain(17)、index(9)、normalized(21)、sources(10)、web(23)、cli/config/init(4)
- 全部 84 个非 attribution 产品模块已由 Java 对应模块接管
- attribution/ 模块（82 个 .py + 19 个 __init__.py = 101 文件）无 Java 对应
- 101 个 scripts/ 文件全部归类为 DEV_TOOL 或 FIXTURE_GENERATOR
- 3 个 CI workflow 为 Java 专用（保留），1 个为 Python 专用（删除）
- Dockerfile 和 docker-compose.yml 为 Python 产品容器（删除）

## Java 对应关系

| Python 模块 | Java 对应 | 状态 |
|---|---|---|
| cli.py, __main__.py | java/app-cli | 已迁移 |
| config.py | java/application AppConfig | 已迁移 |
| domain/ | java/core-domain | 已迁移 |
| sources/ | java/source-claude, source-codex, source-qoder, source-json | 已迁移 |
| index/ | java/index-sqlite, query-api | 已迁移 |
| normalized/ (含 java_bridge) | java/normalization-engine, artifact-normalized | 已迁移 |
| web/ | java/web (Javalin + Pebble) | 已迁移 |
| attribution/ | 无 Java 对应 | NEEDS_DECISION |

## Deletion Order

8 阶段删除计划，详见 PR-INVENTORY-FROZEN.json deletion_order。

## Risks

1. attribution/ 模块（101 文件）无 Java 对应，需用户决策
2. scripts/session-browser.sh 清理时需保留开发命令
3. Python 测试覆盖需确认 Java contract-tests 完全覆盖
4. pyproject.toml 需拆分 runtime 和 dev 依赖
