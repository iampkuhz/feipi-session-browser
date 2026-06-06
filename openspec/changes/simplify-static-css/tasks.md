# 任务：静态 CSS 瘦身

- [x] 1. 盘点 `src/session_browser/web/static/css/` 下 CSS 文件、加载顺序和模板/JS 引用。
- [x] 2. 删除确认不用的历史样式、旧展示块和重复 primitives 定义。
- [x] 3. 删除小视口适配规则，保留桌面端布局约束。
- [x] 4. 运行最小验证并复查 diff。
- [x] 5. 修复导出/内联 CSS 拼接时 `@import` 出现在规则之后导致的编译问题。
