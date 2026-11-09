# 导入分析页面规约

## 定位

导入分析用于查看别人分享的单个 JSONL 会话，提供消息、轮次、工具、token、payload 与 attribution 分析。导入会话不是个人消耗，不计入个人 Dashboard、Sessions、Projects 或其汇总。

## 页面布局

- 上传页路由为 `/imports`，模板为 `import-session.html`；采用统一 Sidebar/Topbar/Main/Content/Footer。
- Sidebar 提供“导入分析”独立入口；上传页和导入详情均高亮该项。
- Page Head 为“导入分析”、一行范围说明及“返回个人 Sessions”。
- 内容顺序为单文件上传表单、分析范围/隐私/临时生命周期说明，不添加个人总量 KPI。
- 成功进入 `/imports/<import_id>`，复用 `session.html` 的当前 Trace 主视图以及 Payload modal/attribution 下钻，不顺带恢复历史 tab。

## 控件和候选项

- 来源为必选项：Claude Code、Codex、Qoder，提交值分别为 `claude_code`、`codex`、`qoder`；默认“请选择来源”，不猜测相似格式。
- 文件控件有明确“JSONL 文件”标签，仅选择单个 `.jsonl`；默认上限为 200 MiB（209715200 字节），MiB 上限由后端传入并在表单显示，`data-max-bytes` 保留精确字节值供前端校验，前端不另定上限。
- 主操作为“导入并分析”；上传期间显示“正在分析…”并禁用重复提交，控件恢复后允许选择新文件或重试。
- 真实 POST `/api/imports` 使用 multipart 字段 `file`、`source`。成功响应的 `detail_url` 必须是当前服务 `/imports/<import_id>`，不得导航到任意外部 URL。

## 文字内容

- 上传页常驻：“查看别人分享的 JSONL 会话；仅分析本文件，不计入个人统计。”
- 导入详情常驻：“导入会话 · 仅本文件分析 · 不计入个人统计”。
- `Total Tokens` 副说明：“仅本文件用量，不计个人总量”。
- 临时链接仅在当前服务实例有效；失效或重启后明确提示重新导入，不承诺永久保存。
- 文件只交给当前本地服务分析，不发送给模型或其他远程服务；分享前仍须由用户检查文件私密内容。

## 数据指标与口径

- 所有用量、轮次、工具和 payload 只来自本次文件；缺少的 sidecar/外部会话不自动补入，不伪造缺失 token。
- 每次导入使用独立 `import_id`，原 `sessionId` 或同名文件不能覆盖个人会话或其他导入。
- 导入前后个人统计、会话列表、项目、趋势和 cache 汇总保持不变；不能只靠前端过滤保证这一点。

## 交互逻辑

- 上传成功后进入独立详情；详情带“导入另一个文件”“返回个人 Sessions”。
- 范围标识在异步数据加载后仍保留，不能放入被 metadata chips 渲染覆盖的容器。
- 详情的 meta/metrics/diagnostics/rounds/payloads/attribution/bucket-detail URL 均跟随导入 API base，不回落个人同 ID 会话。
- 文件名允许换行并保留完整 title；窄宽按单列堆叠，操作换行，不撑宽主内容。

## 状态

- 表单支持未选择、上传中、解析失败、超限、空文件、错选/不支持格式、网络错误与恢复重试；错误采用 `role="alert"`，进度采用 `role="status"`。
- 失败后解除 busy，保留可重试控件；错误仅展示安全消息，不含 JSONL 正文、凭据或服务器临时路径。
- importId 不存在/失效时展示可恢复状态，主操作为重新导入，不能跳入个人详情。

## 禁止项

- 不把导入数据加入个人扫描根或个人统计。
- 不根据 JSONL 中的路径/指令读取本机其他文件或执行命令。
- 不将文件名、错误、原始 JSONL 当作 HTML 注入；使用模板转义和安全 DOM。
- 不显示会错误访问个人同 ID 会话的按钮，不为导入改变当前详情主视图结构。
