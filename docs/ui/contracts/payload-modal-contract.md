# Payload Modal 契约

**版本**: P1 (2026-05-24)
**状态**: 已收敛 — ui-primitives.css 为权威来源

---

## 权威来源

`ui-primitives.css` 中的 `/* --- PayloadModal: authoritative <dialog> primitive --- */` 区块是 `.payload-modal` 组件的 **唯一权威定义**。

包含：
- `.payload-modal` — `<dialog>` 元素全屏透明容器
- `.payload-modal::backdrop` — 原生对话框背景遮罩
- `.payload-modal__panel` — 居中卡片（绝对定位在 dialog 内）
- `.payload-modal__header`、`.payload-modal__title`、`.payload-modal__tabs`
- `.payload-modal__tab`、`.payload-modal__close`
- `.payload-modal__rendered`、`.payload-modal__raw` 及其子元素
- `.payload-modal--sd` — session-detail 变体 modifier

---

## 其他文件角色

### style.css

**不再包含** `.payload-modal` 定义。原有定义（旧 lines 7894-8034）已迁移至 ui-primitives.css。

### session-detail.css

仅保留：
- `.sd-modal-*` 类定义（`.sd-modal-head`、`.sd-modal-body` 等）— session-detail 内部使用的结构类
- `.sd-payload-modal::backdrop` — 唯一遗留覆写
- `.sd-payload-empty-state`、`.sd-payload-diagnostic` 等诊断状态

**已删除**：
- `.session-detail-page #sd-payload-modal` 等 ID 强覆写
- `.session-detail-page .payload-modal` 等长 selector 链
- 媒体查询中的 modal 覆写

页面级差异通过 `.payload-modal--sd` modifier 在 ui-primitives.css 中定义。

### legacy-aliases.css

保留轻量兼容层，标注 `@deprecated`：
- `.payload-modal` — 对齐 primitive 的容器定义（不再独立布局）
- `.sd-payload-modal` — 对齐 primitive 的容器定义
- `.sd-payload-modal__*` 子元素 — 向后兼容的样式别名
- `dialog.payload-modal` / `dialog.sd-payload-modal` — 原生 dialog 元素适配

---

## 模板/JS 使用方式

| 位置 | 元素 | class |
|---|---|---|
| `base.html` | `<dialog>` | `payload-modal` |
| `session_detail_timeline.html` | `<dialog>` | `sd-payload-modal payload-modal payload-modal--sd` |
| `session-detail.js` | 动态创建 `<dialog>` | `sd-payload-modal payload-modal payload-modal--sd` |
| `session_detail_timeline.js` | 动态创建 `<dialog>` | `sd-payload-modal payload-modal payload-modal--sd` |

### 类职责

| 类名 | 来源 | 职责 |
|---|---|---|
| `payload-modal` | ui-primitives.css | 权威 dialog 容器样式（定位、尺寸、backdrop） |
| `payload-modal--sd` | ui-primitives.css | session-detail 变体（更宽面板、更深 backdrop） |
| `sd-payload-modal` | legacy-aliases.css | 向后兼容，布局对齐 primitive |
| `sd-modal-*` | session-detail.css | session-detail 内部结构类（head、body、title 等） |
| `payload-modal__*` | ui-primitives.css | 权威子元素样式（panel、header、tab、rendered 等） |

---

## 明确禁止

以下行为在 CSS contract gate 中标记为 **BLOCK**：

1. **新增裸 `.payload-modal` 全局定义**：不得在 ui-primitives.css 之外新增完整的 `.payload-modal` 规则集。
2. **新增 `#payload-modal` / `#sd-payload-modal` 强覆写**：不得使用 ID selector 覆写 modal 样式。
3. **新增 `!important`**：不得使用 `!important` 提高 modal 优先级。
4. **新增页面级长 selector 覆写**：不得使用 `.session-detail-page .payload-modal` 等长 selector chain 覆写 modal 布局。

### 允许的页面级调整方式

页面只能通过以下方式调整 modal：
- 添加 modifier class（如 `.payload-modal--sd`）
- 使用 CSS custom properties（如 `--modal-width`）
- 使用 `data-*` attributes

---

## CSS 文件归属

| CSS 文件 | 角色 |
|---|---|
| `ui-primitives.css` | **权威来源** — 完整 payload-modal primitive + --sd modifier |
| `style.css` | 不再包含 payload-modal 定义 |
| `session-detail.css` | sd-modal-* 结构类 + 诊断状态 |
| `legacy-aliases.css` | 轻量兼容层（@deprecated），容器对齐 primitive |
