## 导出对象

导出对象为当前 session detail 页面的自包含 HTML/MHTML 文件。文件必须可在无网络环境下通过浏览器直接打开，不依赖任何外部服务。

## 包含内容

- 当前 session 的完整对话内容：round、tool execution、request/response、result 等。
- 页面布局所需的全部 CSS：包括 session detail shell、layout、attribution 等样式。
- 页面交互所需的全部 JS：包括 tabs 切换、modal 弹窗、collapse 展开、trace 展开等。
- 图片和图标：以 base64 内联或 data URI 形式嵌入。
- 字体：以 base64 内联到 CSS 中。

## 不包含内容

- 导航到其他路由的链接目标页面。
- 外部跳转页面或外部文档。
- 其他 session 的内容。
- 需要登录或认证才能访问的资源。
- 动态加载的异步数据（必须在导出前预加载完毕）。

## 交互保真

离线打开时以下交互必须可用：

- Tabs 切换（如 current-session tab、不同 round 的 tab）。
- Modal 弹窗（如 payload 详情、trace 详情）。
- Collapse 展开/折叠（如 request/response body、tool execution result）。
- Attribution 展开（token 归因详情）。
- 搜索和过滤（如 session 内搜索）。

## 文件大小

- 默认上限：50MB。
- 超大 session（如超过 1000 个 round）应有降级策略：提示用户选择导出范围或分段导出。
- 导出文件应在文件头部注释中标注生成时间和版本。

## 失败处理

- 导出失败时应在 UI 中显示明确错误信息，不生成残缺文件。
- 资源内联失败（如找不到 CSS 文件）应中止导出并报告缺失资源。
- 超过大小上限时应提示用户，不静默截断。
