# UI 布局契约：会话详情页

## 硬指标（1440x1100 视口）

这些阈值是**确定性的**——来自 `getComputedStyle` / `getBoundingClientRect`，
而非主观的截图对比。

| 指标 | 阈值 | 失败代码 |
|---|---|---|
| `scrollOk` | `scrollWidth <= viewportWidth + 2` | `HORIZONTAL_SCROLL` |
| `shellGrid` | 不能以 `0px` 开头 | `SHELL_ZERO_COLUMN` |
| `main.width` | >= 1200px | `MAIN_WIDTH_TOO_SMALL` |
| `detail.width` (.session-detail-phase1) | >= 1100px | `DETAIL_WIDTH_TOO_SMALL` |
| `hero.width` | >= 900px | `HERO_WIDTH_TOO_SMALL` |
| `titleBeforeKpis` | `title.bottom <= kpis.top + 4` | `TITLE_OVERLAPS_KPIS` |
| `title.height` | <= 180px | `TITLE_TOO_TALL` |

## 静态 CSS 契约

这些是对 `style.css` 和模板的文本检查：

| 检查项 | 要求 | 失败代码 |
|---|---|---|
| phase1 hide-left 覆盖 | `body.hide-left .shell.phase1-shell` 带 grid-template-columns | `MISSING_PHASE1_HIDE_LEFT_OVERRIDE` |
| phase1 main 网格 | `.shell.phase1-shell .main` 带 `grid-column: 1 / -1` | `MISSING_PHASE1_MAIN_GRID_COLUMN` |
| 详情页宽度契约 | `.session-detail-phase1` 带 width/max-width | `MISSING_SESSION_DETAIL_WIDTH_CONTRACT` |
| hero 单列 | `.session-detail-phase1 .hero-main` 带 `grid-template-columns: 1fr` | `HERO_MAIN_STILL_TWO_COLUMN` |
| 标题换行 | 不含 `overflow-wrap: anywhere` 或 `word-break: break-all` | `HERO_TITLE_UNSAFE_ANYWHERE_WRAP` |
| session shell class 钩子 | `session.html` 声明 `{% block shell_class %}` 含 phase1-shell + no-inspector | `MISSING_SESSION_SHELL_CLASS_HOOK` |
| base shell 应用 | `base.html` 将 shell_class 应用于 .shell | `MISSING_BASE_SHELL_CLASS_APPLICATION` |

## 模板契约

这些是对模板结构的 pytest 检查：

| 检查项 | 文件 | 要求 |
|---|---|---|
| .shell 容器 | base.html | 存在且带 shell_class block |
| .main 容器 | base.html | 存在 |
| shell_class 声明 | session.html | phase1-shell + no-inspector |
| 详情页根节点 | session.html | .session-detail-phase1 存在 |
| hero 标题 | session.html | .hero-title class 钩子 |
| KPI/指标 | session.html | .kpis 或 .metrics-strip |
| trace 行 | session.html | .trace-row class 钩子 |

## 为什么这些是确定性的

所有指标都来自返回精确像素值的浏览器 API：

- `getComputedStyle().gridTemplateColumns` — 解析后的 CSS grid 轨道尺寸
- `getBoundingClientRect()` — 视口坐标中的布局盒几何
- `document.documentElement.scrollWidth` — 总可滚动宽度

没有截图对比，没有主观"看起来不对"的判断。
如果某个指标违反了阈值，门禁会失败，并给出具体的失败代码和 `nextInspection` 指引。
