# 00 Source and Hi-Fi Inputs

## 源码合同

本次改造以本地仓库为准。已确认仓库根目录为：

```
/Users/zhehan/Documents/tools/llm/feipi-session-browser
```

验证项均已通过：

```
test -d src/session_browser/web/templates      # OK
test -d src/session_browser/web/static/css     # OK
test -d src/session_browser/web/static/js      # OK
test -f src/session_browser/web/routes.py      # OK
```

## 高保真合同资源路径

```bash
HIFI_ROOT="/Users/zhehan/Downloads/feipi-session-browser-hifi-integrated-v1"
```

如果目录不存在但 zip 存在，则解压：

```bash
cd "$HOME/Downloads"
unzip -q feipi-session-browser-hifi-integrated-v1.zip -d feipi-session-browser-hifi-integrated-v1
```

## 高保真资源清单

### pages/ — 页面 HTML 合同（10 个）

| 文件 | 对应页面 |
|---|---|
| `pages/dashboard.html` | Dashboard |
| `pages/session-list.html` | Session List |
| `pages/session-detail-metrics.html` | Session Detail - Metrics |
| `pages/session-detail-payloads.html` | Session Detail - Payloads |
| `pages/session-detail-trace.html` | Session Detail - Trace |
| `pages/agents.html` | Agents |
| `pages/agent-detail.html` | Agent Detail |
| `pages/projects.html` | Projects |
| `pages/project-detail.html` | Project Detail |
| `pages/token-glossary.html` | Token Glossary |

### docs/ — 页面说明合同（10 个）

| 文件 | 说明 |
|---|---|
| `docs/dashboard.md` | Dashboard 页面说明 |
| `docs/session-list.md` | Session List 页面说明 |
| `docs/session-detail-metrics.md` | Session Detail - Metrics 说明 |
| `docs/session-detail-payloads.md` | Session Detail - Payloads 说明 |
| `docs/session-detail-trace.md` | Session Detail - Trace 说明 |
| `docs/agents.md` | Agents 页面说明 |
| `docs/agent-detail.md` | Agent Detail 页面说明 |
| `docs/projects.md` | Projects 页面说明 |
| `docs/project-detail.md` | Project Detail 页面说明 |
| `docs/token-glossary.md` | Token Glossary 页面说明 |

### assets/ — 样式与行为资源（22 个）

按页面子目录组织：

| 子目录 | CSS | JS |
|---|---|---|
| `common/` | `common-hifi-rules.css` | `common-hifi-rules.js` |
| `dashboard/` | `dashboard.css` | `dashboard.js` |
| `session-list/` | `session-list.css` | `session-list.js` |
| `session-detail-metrics/` | `session-detail.css` | `session-detail.js` |
| `session-detail-payloads/` | `session-detail.css` | `session-detail.js` |
| `session-detail-trace/` | `session-detail.css` | `session-detail.js` |
| `agents/` | `styles.css` | `app.js` |
| `agent-detail/` | `agent-detail.css` | `agent-detail.js` |
| `projects/` | `projects-list.css` | `projects-list.js` |
| `project-detail/` | `project-detail.css` | `project-detail.js` |
| `token-glossary/` | `token-glossary.css` | `token-glossary.js` |

每个页面对应一个 assets 子目录，包含独立的 CSS 和 JS 文件。`common-hifi-rules.*` 为全局共享规则。

## 高保真资源读取规则

- `pages/` 下每个 HTML 是页面最终视觉合同。
- `docs/` 下每个 markdown 是页面说明合同。
- `assets/` 下 CSS/JS 仅作为视觉/行为参考，不允许直接覆盖源码公共层。
- 先把页面合同提炼到仓库内 `docs/ui/contracts/`，再改实现。
