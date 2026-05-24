# UI CSS 清单

长期维护的 harness 资产。

## 当前预期 CSS 文件

```text
src/session_browser/web/static/style.css
src/session_browser/web/static/css/ui-primitives.css
src/session_browser/web/static/css/session-detail-timeline.css
src/session_browser/web/static/css/sessions-list.css
src/session_browser/web/static/css/session-browser-v15.css
```

## 所有权

| 文件 | 所有者 | 范围 |
|---|---|---|
| `style.css` | design-system | 基础令牌、旧版基础应用外壳 |
| `ui-primitives.css` | design-system-components | 共享原始辅助样式 |
| `session-detail-timeline.css` | session-detail-page | trace / round / tool / subagent 布局 |
| `sessions-list.css` | sessions-list-page | sessions 列表 |
| `session-browser-v15.css` | page-system-v15 | dashboard/sessions/session/projects/agents 的高保真基线 |

新增 CSS 文件时，必须在同一变更中更新此清单。
