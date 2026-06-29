# Session Detail 页面 验收契约

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 会话详情页（hero/trace/metrics/payloads、轮次展开、payload 弹窗、shell 状态） |
| 关联源码 | `java/web/src/main/java/com/feipi/session/browser/web/page/SessionDetailPage.java`、`java/web/src/main/resources/templates/session_detail.html` |
| 关联测试 | `tests/playwright/session-detail.spec.js`、`tests/playwright/session-detail-layout.spec.js`、`tests/playwright/shell-states.spec.js`、`tests/session_detail/` 下 24 个文件、`tests/rendering/` 下相关契约 |
| 主要风险 | shell 状态 CSS 级联冲突导致 main 宽度为 0；payload 弹窗不是 panel 而是全屏覆盖；长会话 DOM 节点爆炸 |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| UI-SD-001 | P0 | visual | 页面加载：hero、问题摘要和 trace 面板可见，无控制台错误 | 访问会话详情 URL | `.sd-hero`、`[data-issue-strip]`、`[data-trace-panel]` 可见，console.errors 为空 | Playwright | snapshot 更新条件：当 hero/trace 面板布局变更时需更新快照 | `tests/playwright/session-detail.spec.js` |
| UI-SD-002 | P0 | visual | 无可见禁用占位按钮 | 检查会话详情页面按钮 | 无 `button:visible[disabled]`，无 `button:visible[title*="待实现"]` | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-003 | P0 | interaction | 所有可见按钮有支持的 data-action | 遍历所有 `button:visible[data-action]` | 每个 data-action 值在支持集合中（filter-status/expand-all/collapse-all/open-payload 等） | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-004 | P0 | interaction | 全部/失败筛选功能正常 | 点击全部/失败筛选 chip | 全部筛选时无 `is-filtered-out` 行，失败筛选时仅失败行可见 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-005 | P0 | interaction | 展开/折叠全部功能正常 | 点击 toggle-all 按钮 | 折叠后 `[data-trace-detail]` 无可见元素，展开后可见元素数 >= 0 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-006 | P0 | interaction | 轮次切换改变 aria-expanded | 点击 `.round-row` 展开详情，再点击折叠 | 点击后详情从 hidden 变为 visible，再点击恢复 hidden | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-007 | P0 | interaction | 首个失败轮次默认展开 | 页面加载后检查首个 `.round-row[data-status="failed"]` 的详情 | 详情元素默认可见（无 hidden 属性且 display 不为 none） | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-008 | P0 | interaction | Payload 弹窗正常打开和关闭 | 点击 `button[data-action="open-payload"]` | 弹窗 `dialog.payload-modal` 获得 `open` 属性，点击关闭后隐藏 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-009 | P0 | visual | Payload 弹窗是居中 panel（非全屏） | 打开弹窗后测量 panel boundingBox | panel 宽度 < 视口 95%，高度 < 视口 90%，宽度 >= 480px，中心点在视口内，无水平滚动 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-010 | P0 | interaction | Metrics tab 切换 | 点击 `[data-tab="metrics"]` | metrics tab 有 `is-active` 类，`[data-tab-panel="metrics"]` 可见，trace 面板隐藏 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-011 | P0 | visual | Token Timeline tooltip 不遮挡 hover 点 | hover token round 后测量 tooltip、鼠标点和 viewport 边界 | tooltip 使用自绘 fixed 浮层，渲染在鼠标上方；靠左时开到右上，靠右时开到左上，不被视口裁剪；带 badge text 的 round 用红色 spike 标记，tooltip 展示完整 Badge Text | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-012 | P0 | interaction | Trace tab 恢复 | 先切 metrics 再切回 trace | trace tab 有 `is-active` 类，trace 面板可见，metrics 面板隐藏 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-013 | P0 | visual | 1440x1100 视口外壳布局正确 | 检查 `.shell` 的 grid-template-columns | 无水平滚动，`.main` 宽度 > 1200px，`.session-detail-page` > 1100px，标题在 KPI 上方 | Playwright | snapshot 更新条件：当 shell CSS grid 变更时需更新快照 | `tests/playwright/session-detail-layout.spec.js` |
| UI-SD-014 | P0 | visual | Shell 四种状态矩阵（normal/hide-left/hide-right/focus）| 通过 JS 设置 body class，测量 grid | normal: sidebar+main>0; hide-left: sidebar=0, main>900; hide-right: inspector=0; focus: sidebar+inspector=0, main>1100 | Playwright | snapshot 更新条件：当 shell.css 变更时需更新快照 | `tests/playwright/shell-states.spec.js` |
| UI-SD-015 | P1 | visual | 会话详情多视口截图（1440x900 / 1280x800 / 1180x800 / 2560x1440）| 各视口截图 | 截图通过视觉回归，maxDiffPixelRatio <= 0.05 | Playwright | snapshot 更新条件：当 UI 布局/设计令牌/颜色变更时需更新快照 | `tests/playwright/ui-contract.spec.ts` |
| UI-SD-016 | P1 | visual | 会话详情模板契约 | pytest 检查模板结构 | 模板含 sd-hero/sd-tabs/trace-panel 区域，CSS/JS 导入正确 | pytest | — | `tests/session_detail/test_session_detail_template_contract.py` |
| UI-SD-017 | P1 | visual | Trace DOM 契约 | 检查 trace 区域 DOM 结构 | trace 行含正确 data 属性；Metrics 只展示 tool count/token 且 tokenbar 按最大 round 比例缩放；round/subround attribution 入口可见文字为 request/response；每个 subround summary 可单独展开/折叠；无 signal 时不渲染占位 badge；round detail 渲染 user message、assistant event、tool call、subagent run 等事件行且不渲染 LLM call card；展开详情中的 user/assistant/tool/result 行使用固定列对齐；tool call 行展示 duration 和 result token estimate，估算值使用 `~` 且与 Result modal 一致；Codex 同文案 event_msg/response_item 关联为一个 assistant event，Assistant Text payload 不重复展示后续 tool call；Codex round 与有效 `event_msg.token_count` LLM call 一一对应，重复 `total_token_usage` 累计快照不建 round 且不计 token | pytest | — | `tests/session_detail/test_session_detail_trace_dom_contract.py` |
| UI-SD-018 | P1 | visual | Trace 布局契约 | 检查 trace 面板布局 | trace 面板无水平溢出，轮次行间距一致 | pytest | — | `tests/session_detail/test_session_detail_trace_layout_contract.py` |
| UI-SD-019 | P1 | visual | Trace 预览契约 | 检查 trace 预览渲染 | 预览行含 tool 命令摘要，状态图标正确 | pytest | — | `java/web/src/test/java/com/feipi/session/browser/web/page/SessionDetailPageTest.java` |
| UI-SD-020 | P1 | visual | Payload 模态渲染器契约 | 检查 payload modal 渲染 | modal 含 payload 内容；tool result modal 的 subtitle 与 metadata rail 展示 `result tokens` 估算值，表示该 result 进入下一次 LLM request 的输入压力且不得标记为 provider reported；归因 modal 使用 topgrid 元信息与全宽分布/明细，request 覆盖率/本地重建/残差字段合并在摘要区且不渲染底部独立覆盖率表格或泛化可能来源尾注；Trace request/response attribution 点击后通过后端 attribution API 按需获取 payload，不在初始页面嵌入完整归因数据；request 归因 bucket 使用全局 token 归因分类树输出 canonical key/category/color/order，并统一中文候选名和颜色；API messages bucket 可解释并展示条目，按当前 call 边界排除未来消息，汇总 token 使用完整条目估算而非 preview，bucket detail 支持贡献来源到子分类再到完整内容的两层展开；内置系统提示有可见内容时展示脱敏 preview、不可见时展示估算说明；Codex request 归因将可见 base/developer/system instructions、function_call_output tool outputs、provider cache read、Codex builtin tool catalog fallback 分别归入可解释 bucket，并通过 taxonomy 显示为统一候选分类；Qoder request 归因将 full_messages_array、provider cache read、Claude-Code-like tool schemas fallback 分别归入可解释 bucket，并通过 taxonomy 显示为统一候选分类；fallback 文案符合预期 | pytest | — | 待补充 |
| UI-SD-021 | P1 | visual | 工具结果渲染 | 检查 tool result 渲染格式 | 不同 tool 类型的结果有正确的格式化展示 | pytest | — | `tests/rendering/test_tool_result_render.py` |
| UI-SD-022 | P1 | visual | Trace 头部契约 | 检查 trace 区域头部 | 含标题、筛选 chip、expand/collapse 按钮 | pytest | — | `tests/rendering/test_trace_header_contract.py` |
| UI-SD-023 | P1 | visual | Session Detail tab 契约 | 检查三个 tab 渲染结构 | metrics/payloads/trace tab 均存在，含 data-tab 属性 | pytest | — | `tests/rendering/test_session_detail_tabs_contract.py` |
| UI-SD-024 | P1 | visual | 预览标签渲染 | 检查 preview tag 组件 | preview tag 含正确的 data 属性和样式 | pytest | — | `tests/session_detail/test_preview_tag.py` |
| UI-SD-025 | P1 | visual | 工具状态渲染 | 检查 tool 状态图标/颜色 | success/error 状态有视觉区分 | pytest | — | 待补充 |
| UI-SD-026 | P1 | data | 缺失 raw payload 处理 | 请求不存在的 payload | 返回 404 错误响应，页面不崩溃 | pytest | — | 待补充 |
| UI-SD-027 | P1 | visual | 长会话（100 轮）渲染性能 | 访问含 100 轮的会话页面 | 页面加载 < 5s，trace 行数 >= 100 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-028 | P1 | visual | 100 轮下 DOM 节点预算 | 折叠/展开后统计 DOM 节点 | 折叠时 < 20k 节点，展开时 < 50k 节点 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-029 | P2 | visual | 噪声和无障碍静态检查 | 检查模板噪声和 a11y | 无多余 console.log 占位，HTML 含基本 aria 属性 | pytest | — | `tests/session_detail/test_session_detail_noise_and_a11y.py` |
| UI-SD-030 | P2 | visual | HiFi 视觉契约 | HiFi 测试会话的完整视觉检查 | 页面含预期的高保真数据展示 | pytest | — | 待补充 |
| UI-SD-031 | P1 | data | Hero subagent 计数 | 构造含 subagent_runs 的 view model | `session_summary.subagent_count == len(subagent_runs)`，slim mode 不依赖 timeline_items | pytest | — | 待补充 |
| UI-SD-032 | P1 | visual | Agents Breakdown 承载 main agent 与 subagent token footprint 信号 | hover main agent round | 页面不再渲染独立 `Main Agent Breakdown`、`Subagent Breakdown`、`Top Token Drivers` 或 `Call Token Footprint Distribution` 卡片；`Agents Breakdown` 候选列表包含 `main agent`；main agent timeline tooltip 不展示 Call Tokens、Call Token Footprint、Top Call、Top Lane 或 main/subagent split；main agent 高 token footprint call 通过 Badge Text 展示，subagent token footprint在 Agents Breakdown 行内展示 | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-033 | P1 | interaction | Trace 深链定位 round 与 subagent round | 打开 `?tab=trace&round=...`，并从 Agents Breakdown 右侧 timeline 跳转 | round 靠近视口顶部；subagent timeline round 写入 `subagent`/`subagentround` 参数并滚动到对应 `SRx` | Playwright | — | `tests/playwright/session-detail.spec.js` |
| UI-SD-034 | P1 | interaction | Hero 展示本地 session 文件路径并支持复制 | 访问会话详情 URL 或检查模板契约 | `[data-session-file-path]` 展示 `.jsonl` 本地路径，复制按钮使用 `data-action="copy"` 且 `data-copy-text` 为完整路径 | pytest | — | 待补充 |
