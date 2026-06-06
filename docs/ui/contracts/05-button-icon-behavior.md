# 05 按钮与图标行为契约

## 全局按钮行为表要求

每个页面必须有一份按钮行为表，字段：

```text
selector / label / location / data-action-or-href / expected render behavior / validation
```

## 全局图标行为表要求

每个页面必须有一份图标行为表，字段：

```text
icon / location / semantic meaning / decorative-or-action / expected behavior / size class
```

## 常用按钮预期

- Settings：打开 settings drawer/panel。
- Info icon：打开就地说明 popover。
- More icon：打开轻量 action menu。
- Apply：提交当前筛选并刷新列表。
- Clear：清空当前筛选并刷新列表。
- Prev：跳到上一页；首页不渲染。
- Page input：输入页码并确认后跳转。
- Next：跳到下一页；尾页不渲染。
- Context / Response / Result：打开同一个 PayloadModal，切换对应内容。

## 图标尺寸

- nav icon: 18–20px。
- metric/card icon: 20–24px。
- inline action icon: 14–16px。

---

## 逐页按钮/图标行为表

逐页详细行为表已记录在各 `behavior-*.md` 文件中：

- `behavior-dashboard.md` — Dashboard 页面
- `behavior-sessions.md` — Sessions 页面
- `behavior-session-detail.md` — Session Detail 页面
- `behavior-projects.md` — Projects 页面
- `behavior-agents.md` — Agents 页面
- `behavior-glossary.md` — Glossary 页面
- `behavior-states.md` — State Pages (404/error)

本文件不再重复各页面摘要，仅保留全局规则。
