---
description: Run remaining feipi-session-browser large-file refactor tasks 02-10 end-to-end with self-validation
argument-hint: [optional extra constraints]
allowed-tools: Bash, Read, Write, Edit, MultiEdit, Grep, Glob, LS, TodoWrite
---

# Feipi Session Browser remaining large-file refactor AUTOPILOT

你正在仓库 `/Users/zhehan/Documents/tools/llm/feipi-session-browser` 中工作。

用户已经在执行任务 01：拆 `src/session_browser/web/routes.py`。本命令的目标是：在任务 01 完成或接近完成的基础上，**自动、端到端、按顺序完成剩余任务 02–10**，并由你自己完成验证、失败分析和修复。不要要求用户中途确认、不要要求用户手工修复、不要把验证留给用户。

你必须把本次工作当作一个保守的、行为不变的结构性重构。核心策略是：**先搬运，后清理；先兼容，后优化；每个阶段自测、自修、再 checkpoint。**

---

## 0. 绝对约束

1. 不读取真实用户会话数据、真实 `~/.claude`、`~/.codex`、`~/.qoder` 内容；只使用仓库测试 fixture、测试数据和公开源码。
2. 不推送远程分支，不创建 PR，不修改远端。
3. 不引入前端 bundler、npm 构建链、Sass/PostCSS/Vite/Webpack，除非仓库已有并且 AGENTS/README 明确要求。
4. 不改变 URL、HTTP status、API JSON shape、数据库 schema、Jinja context 变量、CSS class/id/data-* contract、现有 public import 路径、现有页面行为。
5. 原大文件路径必须继续存在，作为 facade、manifest、wrapper 或兼容入口。
6. 如果需要新增嵌套静态目录，例如：
   - `src/session_browser/web/static/css/session-detail/*.css`
   - `src/session_browser/web/static/js/session-detail/*.js`
   - `src/session_browser/web/templates/components/session_detail_timeline/*.html`
   必须同步更新 `pyproject.toml` package-data，并通过静态 contract / packaging 自检。
7. 不降低测试强度。可以更新测试以匹配新的文件结构，但不能删除关键 contract 检查。
8. 不要等待用户、不要问用户“是否继续”。如果有多个合理方案，选择最保守、最兼容、最容易回滚的方案。
9. 不要使用 `git reset --hard`、`git clean -fd`、删除未跟踪文件，除非这些文件是你本命令刚创建且明确无用的临时产物。
10. 每个阶段结束必须自我验证。验证失败时先修复，再继续。

---

## 1. 工作方式

使用 TodoWrite 维护阶段进度。所有过程记录写入：

```text
.refactor-artifacts/autopilot/
  progress.md
  validation-log.md
  phase-XX-summary.md
  final-self-validation.md
  final-diff-stat.txt
```

启动后先执行：

```bash
cd /Users/zhehan/Documents/tools/llm/feipi-session-browser
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
mkdir -p .refactor-artifacts/autopilot
```

如果存在未提交变更：

- 不要丢弃。
- 先判断是否是任务 01 产生的 `routes.py` 拆分相关变更。
- 如果看起来是任务 01 变更，则把它作为“前置阶段 01 收尾”：运行 compile/test，修复失败，确认 `routes.py` 作为薄入口、旧 URL/import 兼容，然后创建 checkpoint commit：

```bash
git add .
git commit -m "refactor: split web routes handlers"
```

- 如果 commit 失败只是因为本地 git identity 缺失，则设置 repo-local 配置后重试：

```bash
git config user.name "Claude Code Autopilot"
git config user.email "claude-code-autopilot@example.invalid"
```

如果未提交变更看起来不是任务 01，也不要停下来问用户；把当前 diff 保存到 `.refactor-artifacts/autopilot/pre-existing-uncommitted.diff`，然后在不覆盖这些修改的前提下继续。任何冲突都保守处理。

每个阶段按以下循环执行：

```text
读取相关代码和测试
→ 只做该阶段目标内的搬运/拆分/兼容调整
→ 运行目标验证
→ 如果失败，定位并修复，最多重复 5 轮
→ 如果仍失败，判断是否为环境/依赖缺失；只有在证据充分时才记录为环境问题并继续
→ 写 phase summary
→ git diff --stat
→ checkpoint commit
→ 进入下一阶段
```

不要在阶段之间要求用户检查。最终由你输出完整自检报告。

---

## 2. 预检和仓库规则

先读取并遵守：

```text
CLAUDE.md
AGENTS.md
README.md
pyproject.toml
openspec/ 或 AGENTS 中指定的 OpenSpec 规则
tests/quality/test_static_contract.py
scripts/quality/run_quality_gate.py
```

如 `openspec/changes/split-large-files/` 已存在，则继续维护其中 `tasks.md`；若不存在，创建或补齐，但不要中断。每完成一个阶段，在 OpenSpec tasks 中标记对应项目。

---

## 3. 剩余阶段顺序

### 阶段 02：拆 `session-detail.css`

目标：拆分 `src/session_browser/web/static/css/session-detail.css`，保留原路径作为 manifest/wrapper，不改变视觉和 contract。

建议结构：

```text
src/session_browser/web/static/css/session-detail.css
src/session_browser/web/static/css/session-detail/00-tokens.css
src/session_browser/web/static/css/session-detail/01-shell.css
src/session_browser/web/static/css/session-detail/02-header-summary.css
src/session_browser/web/static/css/session-detail/03-tabs.css
src/session_browser/web/static/css/session-detail/04-timeline.css
src/session_browser/web/static/css/session-detail/05-round-detail.css
src/session_browser/web/static/css/session-detail/06-payload-modal.css
src/session_browser/web/static/css/session-detail/07-attribution.css
src/session_browser/web/static/css/session-detail/08-bucket-detail.css
src/session_browser/web/static/css/session-detail/09-anomalies-signals.css
src/session_browser/web/static/css/session-detail/10-responsive.css
src/session_browser/web/static/css/session-detail/99-compat.css
```

执行要点：

- 按注释、选择器前缀、页面区域搬运，不改声明内容。
- `@import` 必须在顶部；或改模板多 `<link>`，但必须保顺序。选择最稳方式。
- 顺序敏感 override 放在后部文件。
- 更新 package-data 和 static contract。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests/quality/test_static_contract.py
pytest tests/session_detail tests/pages/test_sessions_page.py
python3 scripts/quality/run_quality_gate.py --target session-detail --change-id split-large-files || true
./scripts/session-browser.sh test
```

如果 `run_quality_gate.py` 参数不同，先读取脚本帮助或 README，使用仓库实际命令。不要因为命令格式不同就跳过。

Commit：

```bash
git add . && git commit -m "refactor: split session detail css"
```

---

### 阶段 03：拆 `session-detail.js`

目标：拆分 `src/session_browser/web/static/js/session-detail.js`，保留原路径作为兼容入口或 init wrapper，不改变前端行为。

建议结构：

```text
src/session_browser/web/static/js/session-detail.js
src/session_browser/web/static/js/session-detail/namespace.js
src/session_browser/web/static/js/session-detail/dom.js
src/session_browser/web/static/js/session-detail/formatters.js
src/session_browser/web/static/js/session-detail/rounds.js
src/session_browser/web/static/js/session-detail/lazy_rounds.js
src/session_browser/web/static/js/session-detail/tabs.js
src/session_browser/web/static/js/session-detail/filters.js
src/session_browser/web/static/js/session-detail/payload_sources.js
src/session_browser/web/static/js/session-detail/attribution_api.js
src/session_browser/web/static/js/session-detail/attribution_render.js
src/session_browser/web/static/js/session-detail/bucket_detail.js
src/session_browser/web/static/js/session-detail/keyboard.js
src/session_browser/web/static/js/session-detail/init.js
```

执行要点：

- 不引入 bundler/transpiler。
- 推荐 `window.SessionDetail = window.SessionDetail || {};` 单一 namespace。
- 保留测试可能查找的旧符号 alias。
- 如果模板改为多个 `<script>`，必须保证依赖顺序。
- 更新 package-data。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests/quality/test_static_contract.py
pytest tests/session_detail tests/pages
python3 scripts/quality/run_quality_gate.py --target session-detail --change-id split-large-files || true
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: split session detail js"
```

---

### 阶段 04：拆 session detail timeline 模板

目标：拆分 `src/session_browser/web/templates/components/session_detail_timeline.html`，原 include 路径继续存在。

建议结构：

```text
src/session_browser/web/templates/components/session_detail_timeline.html
src/session_browser/web/templates/components/session_detail_timeline/shell.html
src/session_browser/web/templates/components/session_detail_timeline/summary.html
src/session_browser/web/templates/components/session_detail_timeline/round_row.html
src/session_browser/web/templates/components/session_detail_timeline/round_detail.html
src/session_browser/web/templates/components/session_detail_timeline/llm_call.html
src/session_browser/web/templates/components/session_detail_timeline/tool_call.html
src/session_browser/web/templates/components/session_detail_timeline/subagent.html
src/session_browser/web/templates/components/session_detail_timeline/payload_modal.html
src/session_browser/web/templates/components/session_detail_timeline/attribution.html
src/session_browser/web/templates/components/session_detail_timeline/anomaly_badges.html
```

执行要点：

- 使用 Jinja include/macro 拆片段。
- 不改变 CSS class、id、data-*、aria、Jinja context 变量名。
- 原文件作为 wrapper。
- 更新 package-data，确保嵌套模板打包。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests/session_detail tests/quality/test_static_contract.py
pytest tests/pages/test_sessions_page.py tests/pages/test_agent_detail.py
python3 scripts/quality/run_quality_gate.py --target session-detail --change-id split-large-files || true
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: split session detail timeline template"
```

---

### 阶段 05：拆 `sources/qoder.py`

目标：拆分 `src/session_browser/sources/qoder.py`，保持 public facade。

建议结构：

```text
src/session_browser/sources/qoder.py
src/session_browser/sources/qoder_parts/__init__.py
src/session_browser/sources/qoder_parts/discovery.py
src/session_browser/sources/qoder_parts/ids.py
src/session_browser/sources/qoder_parts/models.py
src/session_browser/sources/qoder_parts/token_estimation.py
src/session_browser/sources/qoder_parts/usage.py
src/session_browser/sources/qoder_parts/events.py
src/session_browser/sources/qoder_parts/parser.py
src/session_browser/sources/qoder_parts/diagnostics.py
```

执行要点：

- 先列出 `qoder.py` public functions/classes/constants 和测试 import。
- 搬运纯 helper，再搬 orchestration。
- `src/session_browser/sources/qoder.py` 必须 re-export 旧 symbols。
- 不改变 Qoder short/full/canonical id、token estimation、parse output shape。
- 不读取真实 Qoder 数据。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests -k qoder
pytest tests/web/test_presenter_route_integration.py tests/session_detail
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: split qoder source parser"
```

---

### 阶段 06：拆 `index/indexer.py`

目标：拆分 `src/session_browser/index/indexer.py`，保持 public import 和数据库行为兼容。

建议结构：

```text
src/session_browser/index/indexer.py
src/session_browser/index/schema.py
src/session_browser/index/connection.py
src/session_browser/index/scanner.py
src/session_browser/index/writers.py
src/session_browser/index/queries.py
src/session_browser/index/aggregates.py
src/session_browser/index/maintenance.py
```

执行要点：

- 不改变 SQLite schema，除非已有 migration/测试要求。
- 不改变查询返回 shape 和 scan/index 外部语义。
- `indexer.py` 保留 re-export。
- 依赖方向：schema/connection 底层；queries/writers 依赖 connection；scanner 依赖 writers/queries。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests -k "index or presenter or route"
pytest tests/web tests/pages/test_projects_page.py tests/pages/test_sessions_page.py
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: split indexer modules"
```

---

### 阶段 07：拆 `attribution/agents/claude_code.py`

目标：拆分 `src/session_browser/attribution/agents/claude_code.py`，保持 attribution contract。

建议结构：

```text
src/session_browser/attribution/agents/claude_code.py
src/session_browser/attribution/agents/claude_code_parts/__init__.py
src/session_browser/attribution/agents/claude_code_parts/builder.py
src/session_browser/attribution/agents/claude_code_parts/bucket_normalizer.py
src/session_browser/attribution/agents/claude_code_parts/context_extractors.py
src/session_browser/attribution/agents/claude_code_parts/request_buckets.py
src/session_browser/attribution/agents/claude_code_parts/response_buckets.py
src/session_browser/attribution/agents/claude_code_parts/tool_schema_bucket.py
src/session_browser/attribution/agents/claude_code_parts/usage.py
src/session_browser/attribution/agents/claude_code_parts/residual.py
src/session_browser/attribution/agents/claude_code_parts/safety.py
src/session_browser/attribution/agents/claude_code_parts/constants.py
```

执行要点：

- 不改变 serializer 输出 shape、bucket 名称、UI 依赖字段。
- 不改变敏感信息 masking、truncation、token estimation。
- `claude_code.py` 保留 public facade 或主 builder import。
- 搬运 helper 后补小单元测试，避免只靠 UI 测试兜底。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests -k "attribution or claude_code or session_detail"
pytest tests/test_session_detail_llm_attribution_ui.py tests/session_detail
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: split claude code attribution"
```

---

### 阶段 08：拆 UI primitives

目标：拆分 `src/session_browser/web/static/css/ui-primitives.css` 和 `src/session_browser/web/templates/components/ui_primitives.html`，保留旧入口。

CSS 建议结构：

```text
src/session_browser/web/static/css/ui-primitives.css
src/session_browser/web/static/css/ui-primitives/00-foundation.css
src/session_browser/web/static/css/ui-primitives/buttons.css
src/session_browser/web/static/css/ui-primitives/cards.css
src/session_browser/web/static/css/ui-primitives/forms.css
src/session_browser/web/static/css/ui-primitives/tables.css
src/session_browser/web/static/css/ui-primitives/tabs.css
src/session_browser/web/static/css/ui-primitives/badges.css
src/session_browser/web/static/css/ui-primitives/empty-states.css
src/session_browser/web/static/css/ui-primitives/modals.css
src/session_browser/web/static/css/ui-primitives/utilities.css
```

模板建议结构：

```text
src/session_browser/web/templates/components/ui_primitives.html
src/session_browser/web/templates/components/ui_primitives/buttons.html
src/session_browser/web/templates/components/ui_primitives/cards.html
src/session_browser/web/templates/components/ui_primitives/tables.html
src/session_browser/web/templates/components/ui_primitives/tabs.html
src/session_browser/web/templates/components/ui_primitives/badges.html
src/session_browser/web/templates/components/ui_primitives/empty_states.html
```

执行要点：

- 不改变 macro 名、primitive class 名、视觉行为。
- wrapper 文件继续提供旧 include/import 入口。
- 更新 package-data。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests/ui/test_ui_primitives.py
pytest tests/quality/test_static_contract.py
pytest tests/pages
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: split ui primitives"
```

---

### 阶段 09：清理 `legacy-aliases.css`

目标：缩小 `src/session_browser/web/static/css/legacy-aliases.css`，不要简单拆成更多 legacy 文件。

执行要点：

- 构建 legacy class 使用清单，搜索 templates、static js、tests。
- 删除 alias 必须有 grep/test 支撑。
- 不确定的 alias 保留在 “pending removal” 区域并加 TODO。
- 如果可安全替换为 canonical class，做小步替换并测试。

验证：

```bash
python3 -m compileall src/session_browser
pytest tests/quality/test_static_contract.py
pytest tests/ui tests/session_detail tests/pages
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: prune legacy css aliases"
```

---

### 阶段 10：测试和质量脚本去重

目标：降低 `tests/pages/*.py` 和 `scripts/quality/*.py` 重复度，但不要为了减少行数牺牲测试可读性。

建议结构：

```text
tests/pages/helpers/navigation.py
tests/pages/helpers/assertions.py
tests/pages/helpers/selectors.py
tests/pages/helpers/waiters.py
tests/pages/helpers/fixtures.py
scripts/quality/lib/browser.py
scripts/quality/lib/screenshots.py
scripts/quality/lib/server.py
scripts/quality/lib/assertions.py
scripts/quality/lib/reporting.py
```

执行要点：

- 只抽明显重复的 Playwright 启动、等待、导航、常见断言、截图/reporting 逻辑。
- 不删除关键用户流程断言。
- 不把测试抽象到不可读。
- 质量门禁脚本最后处理，因为它们是安全网。

验证：

```bash
python3 -m compileall src/session_browser scripts
pytest tests/pages
pytest tests/ui
pytest tests/quality
./scripts/session-browser.sh test
```

Commit：

```bash
git add . && git commit -m "refactor: deduplicate tests and quality helpers"
```

---

## 4. 最终全量自检

阶段 02–10 全部完成后，由你自己运行最终验证，不要把验证交给用户。

至少运行：

```bash
python3 -m compileall src/session_browser scripts
pytest tests/quality/test_static_contract.py
pytest tests/session_detail tests/ui tests/pages
./scripts/session-browser.sh test
```

如果仓库 README/AGENTS 指定了 quality gate，运行实际可用命令。先用 `python3 scripts/quality/run_quality_gate.py --help` 或读取脚本确认参数，不要猜错后跳过。

如果改过 package-data 或新增嵌套静态/模板文件，运行：

```bash
python3 -m build
```

并确认构建产物包含新增文件。可以通过解包 wheel/sdist 或列出 archive 内容验证。

最后写入：

```text
.refactor-artifacts/autopilot/final-self-validation.md
.refactor-artifacts/autopilot/final-diff-stat.txt
```

最终报告必须包含：

- 每个阶段完成情况。
- 每个旧入口文件是否仍存在。
- 新模块列表。
- public import / URL / CSS / JS / template / package-data 兼容性说明。
- 每条验证命令和结果。
- 是否有环境性失败；如果有，给出证据和替代验证结果。
- `git log --oneline -n 12`。
- `git status --short`，理想状态应为空；如果不为空，解释每个剩余文件。

---

## 5. 最终回复格式

最终只输出完成报告，不要要求用户再跑测试。格式：

```text
已完成剩余任务 02–10 的端到端重构和自检。

阶段结果：
- 02 ...
- ...

自检结果：
- compileall: pass
- targeted tests: pass
- full test: pass / environment-only blocked with evidence
- package build: pass / not needed

关键兼容入口：
- ...

提交记录：
- ...

最终工作区状态：
- clean / remaining files explained

详细报告：.refactor-artifacts/autopilot/final-self-validation.md
```

不要说“你可以检查/你需要验证”。本任务要求你自己验证。


用户可能在命令后提供额外约束：`$ARGUMENTS`。如果有，遵守这些额外约束，但不能违反上面的绝对约束。
