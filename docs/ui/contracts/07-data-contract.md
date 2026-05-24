# 07 数据契约

## Token 格式化

新增 shared formatter：

```python
def format_compact_token(n: int | float | None) -> str:
    if n is None: return "0"
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.1f}K"
    return str(int(n))
```

## 分页数据

页面模板必须接收：

```text
page
page_size
total_pages
total_count
has_prev
has_next
prev_url
next_url
page_input_url_pattern or form params
```

## 按钮行为元数据

复杂按钮必须含：

```html
<button data-action="..." aria-label="...">...</button>
```

## Payload Modal 数据

Payload modal 统一接收：

```text
payload_id
title
kind: context / response / result / raw / diagnostic
rendered_html
raw_text
missing_reason
```

## Current State（生产代码交叉验证）

### Token 格式化函数

| 函数 | 位置 | None 处理 | M 格式 | K 格式 | 小值 | 匹配 Contract |
|---|---|---|---|---|---|---|
| `format_tokens` | `src/session_browser/domain/token_normalizer.py:282` | `"—"` | `:.1f`M | `:.1f`K | `str(n)` | 部分匹配（None 返回不同） |
| `_format_num_short` | `src/session_browser/web/routes.py:2041` | 无（要求 int） | `:.1f`M | `:.0f`K | `str(n)` | 不匹配（K 用 `:.0f`，无 None 处理） |
| `format_compact_token` | **不存在** | — | — | — | — | 未实现 |

**发现：** 两个现有函数都**不是 Jinja2 过滤器**，也未在模板中直接调用。
Token 格式化在 `routes.py` 层面通过 `_format_num_short` 处理，不通过模板过滤器。
Contract 要求的 `format_compact_token` 尚未实现。

### 分页数据

`sessions.html` 和 `partials/sessions_grid.html` 接收的分页变量：

| Contract 要求 | 当前状态 | 来源 |
|---|---|---|
| `page` | 存在，直接传入 | `routes.py:2009,1965` |
| `page_size` | 存在，类型为 int 或 `"all"` | `routes.py:2010,1966` |
| `total_pages` | 存在，直接传入 | `routes.py:2011,1967` |
| `total_count` | 存在，直接传入 | `routes.py:2008,1964` |
| `has_prev` | 存在，直接传入 | `routes.py:2014,1970` |
| `has_next` | 存在，直接传入 | `routes.py:2015,1971` |
| `prev_url` | 存在，但嵌套在 `actions` dict 中 | `routes.py:647` -> `actions.prev_url` |
| `next_url` | 存在，但嵌套在 `actions` dict 中 | `routes.py:648` -> `actions.next_url` |
| `page_input_url_pattern` | **不存在** | 页面跳转使用 `href` 链接，无 pattern |

**额外变量：** `actions.page_size_urls`（字典）、`page_start`、`page_end`、`sort_key`、`sort_dir`。

### Payload Modal 数据结构

当前存在两套 Payload Modal 系统：

1. **Legacy（base.html）**：`<dialog id="payload-modal">` 含 `payload-modal__rendered` 和 `payload-modal__raw` 两个面板，数据由 JS 动态注入。
2. **Session Detail（timeline 组件）**：通过 `sdp.payload_modal()` 宏或 `payload_modal()` 宏生成完整 modal。

按钮元数据（`open-payload` 触发）：
- `data-payload-id`：存在于 v12 timeline 和 primitives 宏中
- `data-payload-title`：存在于 v12 timeline
- `data-payload-kind`：存在于 v12 timeline（`context`/`response`），但 base.html legacy modal 按钮不含此属性

API 端点 `/api/sessions/{agent}/{session_id}/payload/{payload_id}` 返回完整 payload dict，结构由 `_build_payload_lookup()` 构建，字段包括 `request_payload_raw`、`response_payload_raw`、`payload_missing_reason` 等。

JS 端（`payload_viewer.js`）消费模式：
- `openFullPayloadViewer(payload)` 接收混合字段名（camelCase 和 snake_case 混用）
- 内部 fallback 链：`payload.payload.requestRaw` -> `payload.request_payload_raw`
- `missing_reason` fallback：`payload.payload_missing_reason` -> `pld.missingReason`

### Gap 分析

| Contract 要求 | 当前实现 | Gap |
|---|---|---|
| `format_compact_token` shared formatter | 不存在同名函数 | **需新建** |
| `format_tokens` K 格式 `.1f` | 已实现（与 contract 一致） | 无 Gap |
| `_format_num_short` K 格式 `.0f` | 与 contract `.1f` 不一致 | **需对齐** |
| 模板可访问 token formatter | 未注册为 Jinja2 filter | **需注册** |
| `prev_url`/`next_url` 顶层变量 | 嵌套在 `actions` dict | 可通过模板适配，无阻塞 |
| `page_input_url_pattern` | 不存在 | **需新建** |
| Payload modal `data-payload-kind` | 仅 v12 timeline 有 | **需补齐** |
| Payload modal `rendered_html`/`raw_text` 字段名 | JS 用 camelCase/snake_case 混合 | **需统一** |
| Button `data-action` 全覆盖 | 16 个按钮缺失 | 已有 T012 记录 |
