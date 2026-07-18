## Goal

<一句话描述本次 Session Detail UI 开发目标>

## Allowed scope

- 允许修改的文件列表：
  - `src/templates/` 下 session detail 相关 Jinja 模板
  - `src/static/css/` 下 session detail 相关 CSS 文件
  - `src/static/js/` 下 session detail 相关 JS 文件
  - `scripts/checks/check_session_detail_*.py`（如需）
  - `scripts/checks/*_baseline.json`（如需）

## Forbidden scope

- 不改后端 parser 代码。
- 不改 Java 产品代码。
- 不改 hooks、非 UI 相关的 quality gate 脚本。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不删 required gates。
- 不新增 skip。

## Required reading

- `skills/authoring/feipi-session-detail-ui-dev/references/ui-boundaries.md` — 模板、CSS、JS 边界定义。
- `skills/authoring/feipi-session-detail-ui-dev/references/visual-gates.md` — UI gate 列表和选择策略。
- 目标模板、CSS、JS 文件 — 只读与当前变更直接相关的部分。

## Validation

```bash
python3 -m scripts.checks web.session-detail-static
python3 -m scripts.checks web.css-ownership
```

按需追加：

```bash
python3 -m scripts.checks web.js-action-handlers
python3 -m scripts.checks repository.repo-slimming
python3 -m scripts.checks web.layout-inline-style
python3 -m scripts.checks web.session-detail-static
npm --prefix tests/playwright test -- session-detail.spec.js session-detail-migrated-gates.spec.js
npm --prefix tests/playwright test -- session-detail-layout.spec.js
python3 -m scripts.checks web.raw-innerhtml
```

## Expected output

- 改动的模板、CSS、JS 文件列表。
- CSS ownership 变化（如有）。
- 视觉回归风险评估。
- 门禁运行结果。
- 未覆盖的交互或截图风险。
- 后续风险或 TODO。
