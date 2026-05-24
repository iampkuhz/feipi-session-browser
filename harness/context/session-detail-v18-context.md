# Session Detail 上下文

当前基线模板：

```text
src/session_browser/web/templates/session.html
src/session_browser/web/templates/components/session_detail_timeline.html
```

样式文件：

```text
src/session_browser/web/static/css/session-detail.css     # session detail 页面专属样式
src/session_browser/web/static/css/ui-primitives.css      # 共享原子组件
src/session_browser/web/static/css/legacy-aliases.css     # 向后兼容别名
```

当前观察结果：
- 模态框已居中，元数据侧栏使用裸露文本。
- LLM 调用卡片内的 Response 按钮拉伸过宽。
