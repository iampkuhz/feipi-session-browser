# UI 上下文路由

仅当任务涉及页面结构、CSS、前端 JS、MHTML 导出、视觉验收或 UI 质量门失败时读取本文件。

## 权威来源

| 主题 | 路径 |
|---|---|
| 页面 UI 总览 | `docs/page-ui-specs/README.md` |
| 全局 UI 规则 | `docs/page-ui-specs/common.md` |
| 页面验收清单 | `docs/page-ui-specs/page-acceptance-checklist.md` |
| Dashboard | `docs/page-ui-specs/pages/01_dashboard.md` |
| Sessions | `docs/page-ui-specs/pages/02_sessions.md` |
| Session Detail | `docs/page-ui-specs/pages/03_session_detail.md` |
| Projects | `docs/page-ui-specs/pages/04_projects.md` |
| Token Glossary | `docs/page-ui-specs/pages/07_token_glossary.md` |
| 状态页 | `docs/page-ui-specs/pages/08_state_pages.md` |

## 验证入口

- UI 模板、CSS、前端 JS 变更优先触发 `session-detail` 或对应页面质量门。
- Session Detail 相关变更至少检查 `python3 scripts/quality/run_quality_gate.py --target session-detail --change-id <change-id>`。
- 页面行为若已有 Playwright 或 pytest 契约，必须优先运行对应自动化，不用主观截图判断替代。

## 边界

- 不把页面级旧版本说明恢复到 `harness/`。
- 不在本文件复制完整页面规格；只保留路由。
- MHTML 或离线导出细节优先读取对应代码和 `openspec/specs/mhtml-export/spec.md`。
