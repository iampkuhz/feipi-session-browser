# Session Detail v18 上下文

当前参考：

```text
docs/ui/reference/session-detail-v18-current/
  01-current-modal-metadata-and-llm-card.png
  02-current-expanded-round-layout.png
  current-session-detail-page.mhtml
```

观察结果：
- 模态框已居中，但元数据侧栏仍是裸露文本，视觉上断裂。
- 展开的用户消息 round 丢失了绿色/青色的视觉基调。
- LLM 调用卡片内的 Response 按钮拉伸过宽。

目标：~~docs/ui/hifi/session_detail_v18/index.html~~（已于 2026-05 删除；使用当前 `src/session_browser/web/templates/session.html` + `components/session_detail_timeline.html` 作为基线）

相关仓库事实（来自公开 GitHub）：
- `static/css` 包含多个 CSS 文件，包括规范的 `session-detail-timeline.css` 和旧版本 detail CSS。
- `templates/components` 包含版本化的 session-detail 模板。不要重新引入旧的导入。
