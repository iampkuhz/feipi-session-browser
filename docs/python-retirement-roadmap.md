# Python Retirement Roadmap

本文件记录 Python 到 Java 迁移的退役路线图。当前状态基于 2026-06-25 的 inventory (374 `.py` files)。

## 当前状态快照

| 分类 | 文件数 | 说明 |
|---|---:|---|
| product_runtime | 122 | 核心产品逻辑：解析、归一化、域模型、归因、CLI 入口 |
| product_web | 23 | Web 层：路由、模板、presenter、renderer |
| dev_tool | 64 | 开发工具：UI 检查、QA 脚本、fixture 生成、迁移工具 |
| harness | 39 | Agent harness 基础设施：hooks、validators、OpenSpec |
| quality | 40 | 质量门脚本：契约检查、lint 规则、门运行器 |
| test | 86 | 测试文件：单元测试、集成测试、conftest |

## 退役阶段

### P40C: Remove Runtime Fallback

**目标**: Java 完全替代 Python 在 CLI/scan pipeline 中的运行时角色。

**范围**:
- `src/session_browser/cli.py` -- 已标记 retired，Java launcher 接管 serve/stop/scan
- `src/session_browser/__main__.py` -- 已标记 retired
- `src/session_browser/config.py` -- 环境配置，Java 端已有等价实现
- `src/session_browser/domain/` (19 files) -- 域模型、枚举、归一化，Java core-domain 已对齐
- `src/session_browser/attribution/` (88 files) -- 归因引擎，Java attribution 模块已覆盖

**退出标准**:
- [ ] Java `scan` 命令通过契约测试验证与 Python 输出一致
- [ ] `build.gradle.kts` 中 `python3` 调用迁移到 Java native 实现或标记为显式兼容层
- [ ] `scripts/session-browser.sh` 不再需要 Python venv 启动 scan pipeline
- [ ] `check_no_new_product_python.py` 门控通过

**风险**:
- Attribution 模块复杂度高 (88 files)，需要逐项验证数值一致性
- Token counting (tiktoken) 的 Java 等价实现需要精度验证

### P40D: Migrate Web/BFF/API/Template

**目标**: Java Javalin + Pebble 完全替代 Python Jinja2 Web 层。

**范围**:
- `src/session_browser/web/` (23 files) -- 路由、presenter、renderer、view model
- `src/session_browser/web/routes.py` -- Jinja2 路由 -> Java Javalin 路由
- `src/session_browser/web/template_env.py` -- Jinja2 环境 -> Pebble 环境
- `src/session_browser/web/presenters/` (5 files) -- 页面 presenter -> Java page controller
- `src/session_browser/web/renderers/` (3 files) -- Markdown/LLM blocks renderer -> Java renderer
- `src/session_browser/web/session_detail/` (9 files) -- 会话详情渲染 -> Java session detail

**退出标准**:
- [ ] Java web 模块通过所有 `tests/web/`、`tests/rendering/`、`tests/session_detail/` 契约测试
- [ ] Pebble 模板与 Jinja2 模板渲染输出一致 (`check_jinja_strict_render.py` 验证)
- [ ] `src/session_browser/web/` 整个目录可标记为 deprecated
- [ ] API 端点 (`/api/sessions/*`) 由 Java `SessionApiRouter` 完全处理

**风险**:
- Jinja2 和 Pebble 的 filter 语法差异需要逐一映射
- MHTML 导出功能的 Java 等价实现

### P40E: Cleanup Dependencies/CI/Docs

**目标**: 清理 Python 相关的 CI 依赖、文档和构建配置。

**范围**:
- `build.gradle.kts` 中 3 处 `python3` ProcessBuilder 调用 (lines 254, 432, 486)
- `scripts/quality/doctor.sh` 和 `scripts/harness/doctor.sh` 中的 Python 环境检查
- `scripts/session-browser.sh` 中的 `SESSION_BROWSER_VENV_DIR` 和 venv 逻辑
- `pyproject.toml` 和 `.venv/` 相关配置
- `scripts/quality/` (40 files) -- 质量门脚本迁移或退役
- `scripts/harness/` (14 files) -- harness validator 迁移或退役
- `scripts/claude_hooks/` + `scripts/agent_hooks/` (25 files) -- hook 基础设施

**退出标准**:
- [ ] `build.gradle.kts` 不再通过 `ProcessBuilder` 调用 `python3`
- [ ] CI pipeline 不依赖 Python venv
- [ ] `doctor.sh` 不再检查 Python 兼容性
- [ ] `pyproject.toml` 标记为 deprecated 或删除
- [ ] 质量门脚本的 Python 实现有 Java 等价物或显式保留理由

**风险**:
- Quality gate 脚本数量大 (40 files)，部分与 Java 代码检查深度耦合
- Harness 脚本是 agent 基础设施，退役需要谨慎

### P40F: Final Product Python Removal

**目标**: 最终移除所有产品 Python 代码。

**范围**:
- `src/session_browser/` 整个目录 (145 files)
- `tests/` 中的 Python 测试迁移到 Java JUnit 或保留为契约验证
- `scripts/qa/` (14 files) -- QA UI 检查脚本

**退出标准**:
- [ ] `src/session_browser/` 目录已删除或仅保留空 package
- [ ] 所有契约测试在 Java 端通过
- [ ] `check_no_new_product_python.py` 门控永久通过
- [ ] 文档更新：CLAUDE.md、README 移除 Python 相关说明

**风险**:
- `tests/` 中有 86 个 Python 测试文件，部分测试 Playwright UI 交互，迁移成本高
- `dev_tool` (64 files) 中的 `tmp/` 迁移工具应在 P40E 阶段清理

## 门控策略

`scripts/quality/check_no_new_product_python.py` 脚本确保：
- `src/session_browser/` 中不会新增 `product_runtime` 或 `product_web` 文件
- 已有的 145 个文件作为 allowlist 存在
- `harness/`、`quality/` 中的 Python 维护不受限制
- 任何新增的产品 Python 文件会触发 CI 失败

## 决策记录

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-06-25 | P40 分为 4 个子阶段 | 渐进式退役降低风险 |
| 2026-06-25 | 不立即删除 Python 代码 | 需要 Java 等价实现通过契约验证后才能移除 |
| 2026-06-25 | harness/quality Python 暂不迁移 | 这些是工具链，不影响产品运行时 |
