## CSS 内联

所有 CSS 必须完整内联到导出文件的 `<style>` 标签中：

- 外部 CSS 文件内容必须读取后嵌入。
- `@import` 规则必须展开为实际内容，不允许保留 `@import` 引用。
- CSS 中的 `url()` 引用（如背景图片、字体）必须转换为 base64 data URI 或内联处理。
- 媒体查询和条件规则必须保留完整。

## JS 内联

所有 JS 必须完整内联到导出文件的 `<script>` 标签中：

- 外部 JS 文件内容必须读取后嵌入。
- 不允许保留 `<script src="...">` 外部引用。
- JS 中的动态资源加载（如 `fetch()`、`XMLHttpRequest`）必须在导出前预加载数据并内联结果。
- 第三方库（如已使用的 UI 框架）必须内联其生产版本。

## 图片和字体

- 图片：转为 base64 data URI 嵌入 `<img src="data:image/...">` 或 CSS `background-image`。
- 字体：转为 base64 嵌入 `@font-face` 的 `src` 中。
- SVG 图标：内联 SVG 标记或转为 data URI。
- 大图片（>1MB）可考虑降质或提供占位符，但必须在导出说明中标注。

## 外链禁止

导出文件中不允许存在任何外部网络请求：

- 禁止 `<link href="https://...">` 或 `<link href="//...">`。
- 禁止 `<script src="https://...">` 或 `<script src="//...">`。
- 禁止 CSS `@import url("https://...")` 或 `@import url("//...")`。
- 禁止 CSS `url("https://...")` 或 `url("//...")`（除 data URI 外）。
- 禁止 `<img src="https://...">`（除 data URI 外）。
- 禁止 JS 中的 `fetch("https://...")` 或 `fetch("//...")`。

## 相对路径处理

- 相对路径资源（如 `url(../fonts/...)` 或 `<img src="static/...">`）必须解析为实际文件并内联。
- 不允许保留未解析的相对路径引用。
- 路径解析必须基于项目静态资源根目录，确保不同环境下的一致性。
