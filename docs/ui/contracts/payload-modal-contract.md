# Payload Modal 契约

**版本**: P0 (2026-05-24)
**状态**: 记录 + 后续 P3 迁移

---

## 当前风险

`payload-modal` 组件当前在 **4 个 CSS 文件**中存在定义/覆写：

### 1. style.css (lines 7856-7993)

完整的 `.payload-modal` 组件定义，包含：
- `.payload-modal` 主容器
- `.payload-modal__panel`、`.payload-modal__header`、`.payload-modal__title`
- `.payload-modal__tabs`、`.payload-modal__tab`、`.payload-modal__close`
- `.payload-modal__rendered`、`.payload-modal__raw`
- 内部渲染结构（rendered-section、rendered-row、rendered-code-block 等）

### 2. ui-primitives.css (lines 1331-1617)

另一套 `.payload-modal` 定义，包含：
- `.payload-modal__overlay`（overlay 方案）
- `.payload-modal__dialog`（dialog 方案）
- `.payload-modal__tabs`、`.payload-modal__tab`
- `.payload-modal__metadata`、`.payload-modal__content`
- `.payload-modal`、`.payload-modal__panel`（与 style.css 重复）

### 3. legacy-aliases.css (line 63 + 318-360)

- 压缩单行旧 `.payload-modal` 定义（line 63）
- `.sd-payload-modal` 完整定义（lines 318-327）
- `dialog.payload-modal` / `dialog.sd-payload-modal` 适配规则（lines 358-360）

### 4. session-detail.css (lines 959-1634, 1976-1983)

页面级 `.sd-payload-modal` 覆写和长 selector 覆写：
- `.sd-payload-modal` 主定义（line 959）
- `.session-detail-page #sd-payload-modal` / `.sd-page #payload-modal` 等长 selector（lines 1521-1634）
- 媒体查询中的覆写（lines 1976-1983）

### 模板层

`base.html:169` 在 `{% block legacy_payload_modal %}` 中定义了 `<dialog id="payload-modal" class="payload-modal">`。

---

## 治理目标

1. **最终只能有一个权威 modal primitive**：所有页面共用同一套样式定义。
2. **页面只能通过以下方式调整尺寸**：
   - `data-*` attributes
   - modifier class (如 `.is-large`, `.is-compact`)
   - CSS custom properties (如 `--modal-width`)
3. **页面不得通过以下方式覆写 modal 布局**：
   - `#payload-modal` / `#sd-payload-modal` ID selector
   - `.session-detail-page .payload-modal` 长 selector chain
4. **legacy payload modal 只能作为迁移债务**：不得新增对 `legacy-aliases.css` 中 modal 规则的引用。

---

## 当前阶段：只记录，不迁移

**P0 阶段**：只记录现状，不迁移任何 modal 定义。

**后续 P3**：统一 modal primitive，确定唯一权威定义来源，删除重复定义。

---

## 明确禁止

以下行为在 CSS contract gate 中标记为 **BLOCK**：

1. **新增裸 `.payload-modal` 全局定义**：不得在 style.css、ui-primitives.css 之外新增完整的 `.payload-modal` 规则集。
2. **新增 `#payload-modal` / `#sd-payload-modal` 强覆写**：不得使用 ID selector 覆写 modal 样式。
3. **新增 `!important`**：不得使用 `!important` 提高 modal 优先级。

> 注意：P0 阶段不将历史遗留的 payload-modal 多定义问题升级为 BLOCK，因为已有大量历史定义。
> 仅对 **新增** 的违规定义执行 BLOCK。

---

## CSS 文件归属

| CSS 文件 | 当前角色 | 未来角色 |
|---|---|---|
| `style.css` | payload-modal 主定义之一 | 待定 (P3) |
| `ui-primitives.css` | payload-modal primitive 定义 | 可能成为权威来源 (P3) |
| `legacy-aliases.css` | 旧 payload-modal + sd-payload-modal | 迁移后删除 |
| `session-detail.css` | 页面级 modal 覆写 | 应通过 modifier/CSS variable 实现 (P3) |
