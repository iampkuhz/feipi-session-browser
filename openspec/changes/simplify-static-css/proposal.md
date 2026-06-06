# 提案：静态 CSS 瘦身

## 背景

`src/session_browser/web/static/css/` 已经按 tokens、base、shell、ui-primitives、页面 CSS 分层加载，但历史迁移过程中保留了部分旧选择器、旧注释和页面内重复定义。它们会增加维护成本，并提高未来样式冲突概率。

## 目标

- 保留现有 CSS 分层架构。
- 删除当前模板、JS 和加载顺序中确认不用的 CSS。
- 删除移动端、平板或小视口专属适配规则。
- 收敛页面 CSS 中与共享 primitives 重复的定义。

## 非目标

- 不重写页面 HTML 结构。
- 不改变 JS 交互行为。
- 不新增移动端或平板端支持。
