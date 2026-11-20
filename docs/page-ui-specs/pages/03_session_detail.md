# Session Detail 页面规约

- Token KPI、缓存比例、round/call/subagent、attribution 遵循 `common.md` 的 `Token Measurement Provenance`。session 级估算不复制到无 usage 的 call；未知输入不进入低缓存筛选或伪造 0% 折线，导入 scope 保持独立。

## 定位

Session Detail 是单个 session 的运行分析页。默认先回答已观察到什么失败、同名工具已测最长项及证据覆盖，再展示可扫读的响应分组动作；Token、缓存、上下文和完整记录按需查看。只保留 `Trace`、`Payload` 两个主入口。

## 页面布局

- 路由固定为 `/sessions/<agent>/<session_id>`；模板固定为 `session.html`；HTML 和 MHTML 下载入口见 [Session Export Contract](../../session-export-contract.md)。
- 面包屑固定为 `Dashboard / Sessions / <agent> / <short session id>`。
- 默认顺序为身份摘要、Trace/Payload 入口、执行判断、紧凑执行过程、按需 Token 分析与完整记录证据。
- 身份摘要默认只保留标题、agent 和原生“会话信息”展开入口。session id/file copy、model/project、原始标题、绝对时间和旧问题摘要保留在会话信息内，支持键盘展开，不占默认首屏。
- `Total Tokens`、`Cache Health`、`Workload`、所有诊断卡片及原 Trace round 证据完整保留在过程后的原生 details；`Run Health` 与 `Source Task Active` 保留二级入口。
- 诊断卡片区固定包含 `Agents Breakdown`、`Context Budget`、`Tool Impact`、`Issues & Repro Seeds`。
- 主内容区固定包含 `Trace`、`Payload` 两个 tab。
- Trace 默认请求有界执行摘要，不展开每个 Round 或预载正文。响应 header 与缩进保留声明归属；同组跨页标记为续组。旧 round table 为按需证据工作区，仍支持筛选、分页、归因和深链。
- 实际命令/参数短预览为操作行主信息；工具类别、状态和时长就近显示。证据入口不独占每条短工具行，长内容自然换行，无固定高度裁切。
- 每个响应 header 提供一对模型输入/模型输出入口，不在每个工具重复；无可用本地证据时明确未记录。输入只表示本地可见来源或关联结果，不等同完整 HTTP。诊断卡给具体操作短摘要，kind 等实现枚举只在按需说明/来源证据内。
- 过程组头默认可见显示已有记录类型和 `#N`，区分模型响应记录与独立调用边界未确认的本地响应记录；编号仅用于本地定位，不是实际 provider 请求次数。单动作记录在桌面尽量紧凑，多工具保留组头与动作边界，不为单行隐藏记录类型。工具响应短正文下沉至记录来源，纯文本响应仍默认展示；长命令及窄屏自然折行。
- 命令摘要仅从明确的 `cmd`/`command`/`script` 结构字段或单次静态 `tools.exec_command` 包装提取，不执行脚本，不按变量名硬编码；动态/多调用/未知语法回退原文，多语句仍是一项工具调用。
- 明确且唯一的typed委派/追加输入声明可在现有工具主摘要优先显示“委派任务：…”/“追加输入：…”安全文本，完整target、控制字段及原Input/Result仍按需。资格绑定冻结scope与完整工具occurrence，不以裸名/message/结果猜测；未知/冲突/非法/非文本或无法诚实概括的混合输入保持原安全预览。catalog/inline和normal/import同策略，保留严格解析、脱敏、64×1024字符参数/180字符摘要预算；不改等待工具、原名/计数/计时/定位，不新增DTO、默认请求、面板或送达/采用语义。
- 按需工具 Input 对有界、未截断、仅含一个 `cmd`/`command`/`script` 字符串字段且值为多行的完整 JSON，优先用纯文本保留原换行和缩进；完整原始参数放入原生 details，命令文本和原始参数分别复制。重复键、多字段、嵌套/动态包装、无效/非字符串/超界或单行参数仍按原样展示。不执行或拆分脚本、不重新计数、不增加默认正文请求，也不恢复已遮盖内容；不改模型输入/输出或工具结果。
- 工具执行结果弹框为 metadata 在上、结果正文在下的全宽布局；明确 `output`/`result` 或受支持的 `Script completed…Output:` 包装优先展示正文，完整包装及声明命令保留按需入口和独立复制。未知、歧义、非文本或超出提取界限时展示完整结果记录，空输出不冒充缺失；模型输出与工具输出不混为一层。
- Payload tab 打开后才请求有界载荷索引；逐项共用现有原文/归因弹框，不自动爬取所有页或正文。
- HTML 和 MHTML 是静态离线归档：保留已发布的调用、工具、正文、归属和 token 计量，用原生控件展开，不复制在线 tab、筛选和弹框。

### 导入分析范围

- `/imports/<import_id>` 复用当前详情模板的 Trace 主视图及 Payload modal/attribution 下钻，不为导入改变主视图结构；完整入口行为见 `09_imports.md`。
- 导入详情面包屑为 `导入分析 / <filename>`，主导航高亮导入分析。
- Hero 前常驻“导入会话 · 仅本文件分析 · 不计入个人统计”，并提供“导入另一个文件”“返回个人 Sessions”；范围提示不能被异步 metadata 加载替换。
- `Total Tokens` 的 label 与 aria-label 保持不变，增加“仅本文件用量，不计个人总量”副说明。
- 所有 round/payload/attribution/bucket-detail 请求均来自 `/api/imports/<import_id>`；原来源 session ID 不能导致回落个人 API。
- 导入详情不暴露服务器临时路径，不提供会错误访问个人同 ID 会话的导出按钮；个人详情与离线导出行为保持。

## 文字内容

- 主 tab 文案固定为 `Trace`、`Payload`。
- Hero KPI label 固定为 `Run Health`、`Total Tokens`、`Cache Health`、`Workload`、`Source Task Active`。
- Hero 本地文件路径行 label 固定为 `Session file`，展示索引或解析阶段定位到的本地 JSONL 绝对路径；路径缺失时不渲染该行。
- Hero 本地文件路径行必须提供 `Copy session file path` 按钮，按钮使用统一 `data-action="copy"` 和完整 `data-copy-text` 路径，供用户直接粘贴到终端或编辑器。
- 每张一级 KPI 下方二级 KPI 数量允许为 0-4；实际 Session Detail 首屏每张卡保留 3-4 个高信息量二级 KPI，不为了视觉对齐添加低价值指标。
- 每个一级 KPI 和二级 KPI 必须提供 tooltip，解释当前指标口径、分母、来源或定位入口。
- 诊断卡标题固定为 `Agents Breakdown`、`Context Budget`、`Tool Impact`、`Issues & Repro Seeds`。
- Trace table 列名固定为 `Round`、`Summary`、`Metrics`、`Signals`、`Time`。
- Payload 右侧标题固定为 `Selected Call Detail`。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时显示 unavailable 原因、precision 和 source，不用空白区域代替。

## Hero KPI

### Run Health

- 一级值固定为 `Completed`、`Completed with issue signals`、`Failed` 三选一。
- 二级指标固定为 `Issue Rounds`、`Failed Tools`、`Payload Gaps`、`Attribution Gaps`。
- `Issue Rounds` 表示含 tool failure、LLM error、payload gap、attribution gap 或 session anomaly 的 round 数。
- `Failed Tools` 使用全局失败 tool call 口径，并展示 `失败数 · 失败率`；失败率按比例标记 ok/warn/bad 色。
- `Payload Gaps` 表示 Payload tab selector item 中 `missing` 或 `error` 的缺口数量。
- `Attribution Gaps` 表示 request/response attribution 构建失败或不可用的数量。
- 只要 Tool failure、LLM error、payload missing、attribution error 任一存在，Hero issue strip 不得显示 `No issue signals`。

### Total Tokens

- 一级值：`Fresh + Cache Read + Cache Write + Output`。
- 二级指标固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`。
- `Fresh` 表示互斥的新输入分段；当 provider 的 Cache Read 是 input token 子集（例如 OpenAI/Codex `cached_input_tokens`）时，Fresh 使用 `input_tokens - cached_input_tokens`，避免 Total 重复计入缓存命中输入。
- `Cache Read` 表示 provider reported Cache Read input token。
- `Cache Write` 表示 provider reported cache creation/write input token。
- `Output` 表示模型可见输出 token，不把隐藏 reasoning token 混入该值。
- Codex 以带明确响应身份的 `token_usage_record` 作为独立模型调用边界；仅有旧版累计计数时，有正向组件增量且能闭合的 `event_msg.token_count` 可作为边界。镜像或重复计数不增加调用数或 token；证据不足时显示记录分组，不推断真实模型调用。assistant 文本是展示材料，不是计量边界。
- Codex 重复 `total_token_usage` 累计快照不得创建 round、不得贡献 token；诊断中必须保留 record index、timestamp、累计 total 和 `contribution=0`。
- 四个二级指标合计必须等于一级值；无法和来源总量对齐时一级值仍显示互斥 component sum，tooltip 说明 component sum、source total、缺失字段、来源和精度。
- 四个二级 token 指标展示 `绝对值 · 占比`，占比相对 Total Tokens，并按占比标记颜色。

### Cache Health

- 一级值：`Cache Read / (Fresh + Cache Read + Cache Write)`。
- 二级指标固定为 `Input-side Tokens`、`Low-cache Rounds`、`Fresh Spike Rounds`。
- `Input-side Tokens` 表示 `Fresh + Cache Read + Cache Write`。
- `Low-cache Rounds` 表示 round-level Cache Read ratio 小于 20.0% 的 round 数。
- `Fresh Spike Rounds` 表示 fresh token 高于当前 session round fresh token 中位数 2 倍的 round 数。
- 分母为 0 时一级值显示 `N/A`，tooltip 展示 `Input-side Tokens = 0`。

### Workload

- 一级值：主 agent 和 subagent 的归一化记录总数。
- 二级指标为 `Main records`、`Subagent records`、`Tool Calls`、`Subagent Runs`。
- `Main records` 表示归一化的主 agent 记录数，不等同于已验证的模型调用数。
- `Subagent records` 表示归一化的子 agent 内部记录数，不计入主 agent。
- `Tool Calls` 使用全局 tool call 总数；如需展示主 agent 口径，只在 tooltip 或 Tool Impact 中说明 `Main tools`。
- `Subagent Runs` 表示独立 subagent 上下文启动次数。

### Source Task Active

- 一级值为 typed `timing.activeTaskSeconds`，仅 MAIN 源任务窗口 union，非模型推理。
- 二级指标固定为 `Wall Duration`、`Agent Turn`、`Model Execution`、`Tool Execution`。
- 遵循 `common.md` typed timing 精度；缺来源显示 `N/A`，不使用 legacy execution/0 或跨夜 transcript span 补齐。
- 常驻说明 task-window union 包含工具/等待，Agent Turn 是独立累计 workload；列出 completed/incomplete/aborted 计数和 basis。
- 只有 wall/task 均 measured 才显示 `Non-task Wall Time` 差值，明确不等同用户等待。
- 在线执行判断附近仅在全部或主会话范围、且同代 `activeTaskSeconds` 或 `agentTurnSeconds` 有合法 measured/partial 值时，提供“主会话任务／轮次计时”的次级查看入口，合法实测 0 也可用。点击才展开现有 Token 分析与运行诊断祖先并聚焦、滚动到本卡，不复制数值或新增面板/请求；子 Agent、匿名范围及两项均未知时不显示。指标迟到只更新入口，不自动展开或抢焦点；范围/冻结代失效撤销旧事实。任务窗口、Agent Turn、逐工具观测及模型执行口径保持独立，不以差值推模型，不将 MAIN 计时归属子 Agent；离线能力不扩大。
- 显式进入计时卡后，先前挂起的工具定位或子上下文重置即使随后完成，也只应用数据，不把焦点/视口拉回工具或诊断；复用既有意图取消与返回保护，不另建全局焦点框架。
- 同代有效、仍聚焦且渲染前完整可见的同一卡片若被该次过程渲染推离视口，只补偿原位布局偏移；用户已滚离、转焦或冻结资格失效则不补偿，不重新聚焦/展开，不监听全局滚动。

## 诊断卡片

### 诊断区整体排版

- 宽屏 `>= 1440px`：诊断区使用 2 列 grid。
- 宽屏第 1 行：`Agents Breakdown` 跨 2 列。
- 宽屏第 2 行：`Context Budget` 跨 2 列，独占整行。
- 第 3 行保留 `Tool Impact`、`Issues & Repro Seeds` 两个按需入口；Tool 默认收起，Issues 有线索时自动展开。桌面并列、窄屏单列。
- 标准桌面 `1024px-1439px`：诊断区保持 2 列 grid；`Agents Breakdown` 跨 2 列，`Context Budget` 跨 2 列独占整行，`Tool Impact` 与 `Issues & Repro Seeds` 的摘要左右排列。
- 窄屏 `< 1024px`：诊断区改为单列，全部卡片按固定顺序纵向排列。
- 默认分析卡 header 为 44px；按需入口允许摘要回流，body 不保留空白占位高度。
- 诊断卡不嵌套子卡；内部 stat 使用 compact stat 行，表格使用 `common.md` 的 `Compact Table`。

### Agents Breakdown

- 卡片定位：统一展示 main agent 和 subagent 的 token 构成、cache reuse 健康度、高token footprint call、工具调用和失败，是 Session Detail 的第一诊断入口。
- 卡片必须跨 2 列占整行，内部固定为 1/3 + 2/3 两列布局。
- 左侧 1/3 为 agent 候选列表和摘要信息；第一项必须是 `main agent`，后续为每个 subagent run。
- 每个候选行必须单行展示 agent name、短 id、LLM calls、Footprint Tokens、Tools、Failures。
- 左侧列表最多同时显示 5 个候选；超过 5 个时列表区域固定高度并在内部上下滚动，不得继续撑高整张卡片。
- `main agent` 默认选中；点击候选行时只切换右侧 timeline，不直接跳转 Trace。
- `main agent` 的 `Footprint Tokens` 使用主 round token 合计；subagent 的 `Footprint Tokens` 表示 subagent 内部 LLM token、父 Agent result token、内部 tool result token 的 footprint 合计，tooltip 必须拆分来源。
- subagent Token Driver 的 tokens、share、reason 必须合并到对应 subagent 行的 tooltip 或 compact metadata，不再单独出现在 Top Token Drivers 表格。
- 右侧 2/3 展示选中 agent 的 token/cache timeline，图表类型固定为按 round 顺序排列的堆叠柱状图。
- `main agent` x 轴显示 session round number，标签格式固定为 `R1`、`R2`、`R3`；subagent x 轴显示 subagent round，标签格式固定为 `SR1`、`SR2`。
- 左 y 轴显示 total tokens，轴标题固定为 `Tokens`。
- 右 y 轴显示 Cache Read ratio，轴标题固定为 `Cache Read %`，范围固定为 0% 到 100%。
- 堆叠顺序固定为 Fresh、Cache Read、Cache Write、Output。
- Cache Read Ratio 以折线叠加在柱状图上；折线只使用右 y 轴。
- 低缓存 round、fresh spike round、payload missing/error round 不在柱子附近显示文字 badge；命中任一诊断标签时，只在该 round 下方显示一个红色 spike 三角 marker。
- 点击 `main agent` 柱子跳到 Trace 对应 round，并写入 `tab=trace&round=<round_number>`；点击 subagent 柱子写入 `subagent`/`subagentround` 参数并滚动到对应 `SRx`；目标必须靠近视口顶部，不得居中或偏下。
- 不渲染配套明细表；round 和 call 细节通过 `common.md` 的 `Chart Tooltip` 展示。
- `main agent` tooltip header 固定展示 round id 和 round start time；subagent tooltip header 固定展示 subagent round、parent round 和 start time。
- tooltip 行顺序固定为 `Fresh`、`Cache Read`、`Cache Write`、`Output`、`Total`、`Cache Read Ratio`、`Calls`。
- tooltip value 列右对齐，share 列右对齐，Total 行上方显示 separator。
- tooltip 使用共享 `TokenProvenance` viewport popover；支持 hover、键盘 focus、Escape，按触发点和视口边缘限制位置，不被表格/图表容器裁剪。
- tooltip note 区使用 `Badge Text` 作为标签名，展示 缺省处理、missing usage、fresh spike、low cache、payload gap、Token Driver 中命中的完整 badge 文本；红色 spike 三角只作为“该 round 有 badge text”的视觉提示，不承载截断文本。
- 命中 Top 5 Token Driver 的主 agent call 必须在对应 round 的 `Badge Text` 中展示完整 driver、tokens、share、model。
- `Call Token Footprint Distribution` 和 `Top Token Drivers` 不再作为独立诊断卡渲染；timeline tooltip 不展示 `Call Tokens`、`Call Token Footprint`、`Top Call`、`Top Lane` 或 main/subagent split。main agent token footprint由本卡 tooltip 表达，subagent token footprint由本卡候选行表达，tool result token footprint由 `Tool Impact` 表达。
- tooltip 中 `Fresh`、`Cache Read`、`Cache Write`、`Output` 使用对应颜色方块；`Cache Read Ratio` 使用对应颜色短横线。
- 下方不渲染重复 compact stat；`Input-side Tokens`、`Cache Read Ratio`、`Fresh Spike Rounds`、`Low-cache Rounds` 已在 Hero KPI 或 tooltip 中表达。

### Tool Impact

- 卡片定位：展示工具调用体量、失败和结果 token 压力。
- 不在顶部渲染 compact stat；全局汇总固定合并到表格底部 summary 行。
- `All Tool Calls` 使用全局 tool_calls 总数。
- 表格行数固定为 top 5 tools，排序优先级为调用次数、result token、tool name。
- 列固定为 `Tool`、`Calls`、`Result Tokens`、`Failures`。
- `Failures` 展示 `失败数 · 失败率`，失败率按比例标记 ok/warn/bad 色。
- tooltip 必须拆分 `Main` 与 `Subagent` 调用数，避免 Hero 和表格口径冲突。

### Issues & Repro Seeds

- 卡片定位：沉淀可复现缺陷线索，服务 UI 质量门、parser 回归和 payload 诊断。
- 不渲染顶部类型聚合卡；问题类型聚合用于排序和 Hero issue strip，不在卡片内重复展示。
- 表格行数固定为最高严重度的 5 条问题。
- 列固定为 `Issue`、`Evidence`、`Round`、`Locator`。
- `Issue` 示例值：`Tool failure`、`LLM error`、`Payload gap`、`Attribution error`。
- `Evidence` 示例值：`Bash exit 1`，最长 160 字符，超出后截断。
- `Round` 示例值：`R3`，点击跳到 Trace 对应 round。
- `Locator` 展示 `Copy locator` 操作，点击复制完整复现定位串，定位串格式包含 session、round 和 payload/tool/call id。
- severity 不单独占列，通过 `Issue` badge tone 表示：critical 使用红色，warning 使用琥珀色，info 使用灰色。
- 已分析且没有线索时展示“未发现可操作的问题线索”；未分析显示未测量，不是 0 条；有失败时 Hero 不得显示 `No issue signals`。

### Context Budget

- 卡片定位：解释当前 session 用量的可验证构成，而非模型 context window 占用率。
- 图表类型固定为水平分段条形图。
- 分段来自 DTO 的真实分类/纳入状态；Tool Results 是构成之外的本地估算，不塞进构成条。
- x 轴显示 token share，范围固定为 0% 到 100%。
- y 轴只有一行，标题固定为 `Session Context`。
- 分段条可在空间足够时内嵌分类名和占比；窄分段隐藏内嵌文字，但保留 tooltip。
- 下方 legend 使用 `auto-fit` 内容驱动网格，标签、数值、占比和来源就近排列；长标签完整回流，窄屏不溢出。顺序/色标与构成条一致，不按页面复制样式。
- 不渲染配套明细表或每分类独立 progress track；细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip 固定展示 `Segment`、`Tokens`、`Share`、`Source`、`Precision`。
- 当前卡标题右侧显示“会话级构成”。
- 仅明确纳入且有可用 share 的分段参与构成；Partial 为近似、非服务商精确统计。未知/未上报/不可用显示中文原因，不补 0%；实测零保留 0%。缓存比率仅使用完整服务商上报输入，分母不含 Output。

## Trace Tab

### Trace Tab 目标

- Trace 是默认打开的 tab，是当前仓库最高频调试入口。
- Trace 默认以 table 形态展示 round 列表，保证长 session 能快速扫描、排序和定位失败。
- Round 展开后使用 step card 形态展示详细过程，吸收高保真稿中可读性更好的时间线结构。
- Trace 和 Payload 使用同一 call id、round id、payload id，必须能互相定位。

### Trace Toolbar

- toolbar 左侧固定展示说明文案：`Round 内按时间顺序纵向推进；并发 tool calls 作为一个 batch 分组显示。`
- toolbar 右侧固定展示 status segmented control 和 expand control。
- status segmented control 候选项固定为 `All`、`Failed`、`Low cache`。
- `Low cache` 展示 round-level Cache Read ratio 小于 20.0% 的 round，用于定位 Hero `Low-cache Rounds`。
- expand control 是一个全局 toggle，文案固定在 `Expand all` 和 `Collapse all` 之间切换。
- 后续加入搜索控件时，搜索框固定放在 toolbar 左侧说明文案下方，不改变 status segmented control 的位置。
- Trace filter 状态必须写入 URL 参数 `trace_status`。

### Trace Round Table

- 表格固定使用 6 列：`Round`、`Summary`、`Metrics`、`Attribution`、`Signals`、`Time`。
- `Round` 列宽固定为 72px，展示 `R<round_number>` 和状态色。
- Codex 的 `R<round_number>` 表示第 N 个有效 LLM call round，而不是第 N 个可见 assistant 文本窗口；无可见文本但有 tool_use 或 usage 的 Codex call 也必须保留为 round。
- `Summary` 列占剩余主宽，展示当前轮短摘要：优先可见用户输入，其次工具名称/次数与短操作预览，再回退助手文本。必须解析当前调用的 inline/catalog/sequence 引用，过滤系统上下文及工具结果；不得跨轮借文或嵌入长代码/输出。真正缺失显示 `摘要未记录`。
- `Metrics` 列宽固定为 220px，展示本地归一化调用记录数（`records`）、当前声明的工具执行数（`tools`）和 `Token Cell`；tooltip 必须解释 records 不是独立 provider 请求数，消费历史工具结果不计为新执行。
- `Token Cell` 的彩色 tokenbar 宽度必须按当前 session 最大 round token total 归一化，最大 round 为满宽，其他 round 按比例缩短；未占用的轨道使用灰色背景显示与最大 round 的差距。
- `Attribution` 列宽固定为 180px，展示 main request/response attribution 入口；按钮可见文字固定为 `request` 和 `response`，title/tooltip 可展示 call id、payload id、覆盖率和可用性。
- `Signals` 列宽固定为 180px，只在命中 `Failed`、`Subagent`、`Payload Gap`、`Attribution Gap` 时展示对应 badge；无信号时保持空白，不显示占位 badge。
- `Time` 列宽固定为 132px，展示当前调用或其响应来源引用中第一个已记录的时间点（Asia/Shanghai）；无源时间显示 `未记录`，不用 session 更新时间或耗时代替。
- `Summary` 示例值：`Fix template macro scope`，表示该 round 的主要动作摘要。
- `Metrics` 示例值：`2 tools · 24.1k`，token 数值后跟比例化 `Tokenbar`。
- `Attribution` 示例值：`request · response`，按钮 title 展示 call id、payload id 和覆盖率。
- `Signals` 示例值：`Failed`、`Subagent`、`Payload Gap`、`Attribution Gap`。
- `Time` 示例值：`14:23:11`，tooltip 展示完整 timestamp、round duration、process time。
- table header 中只有 `Metrics` 的 token 排序入口可点击，排序字段固定为 total tokens。
- 当前展开 row 必须有明确背景色和行内状态线；状态线不得超出 row 自身边界或侵入相邻 round。

### Expanded Round Detail

- expanded detail 只在当前 round 展开时渲染。
- detail 内部固定为一条纵向 event timeline，左侧是 timeline rail，右侧是紧凑事件行。
- detail 面板必须与展开 round 行和下一条 round 行保持可见间距；detail 外框不得与上下 round 边框贴合或重合。
- step 顺序固定为原始 trace 顺序；assistant thinking/text、tool_use、tool_result、subagent run 必须按 timestamp 排列。
- step 类型为 `User Message`、`Assistant Thinking`、`Assistant Text`、`Tool Call`、来源工具组、`Tool Result`、`Subagent Run`、`System Signal`；同组多工具只表示声明来源，缺少可信执行区间重叠证据不得称为 `Parallel Tool Group`。expanded timeline 不渲染 `LLM Summary` 或独立 `LLM Call` card。
- `User Message` 行展示 role、摘要、timestamp、输入 preview；preview 最长 3 行，长内容从 payload 打开。
- `Assistant Thinking` 行展示 thinking 摘要、timestamp、source block 和 payload 入口；必须使用与 `Tool Call` 行同等高度的单行紧凑布局，长文本单行截断。
- `Assistant Text` 行展示对用户可见文本摘要、timestamp 和 payload 入口；必须使用与 `Tool Call` 行同等高度的单行紧凑布局，长文本单行截断。该行 payload 只展示 assistant text / thinking 内容，不重复展示同一 LLM response 中已经在后续 `Tool Call` 行平铺展示的 tool call。
- Codex 原始 JSONL 中同一 assistant 文案可能同时出现为 `event_msg.agent_message` 和 `response_item.message role=assistant`；Trace 必须把两者关联为同一个 assistant text 事件，优先使用 `response_item.message` 作为 canonical payload source，`event_msg` 只作为 UI/status mirror 或缺省处理，不得重复展示两行相同文本。
- 单调用行的 Request/Response 不在展开内容中重复；多记录分组在展开后提供各成员的 Request/Response，正文与归因使用同一弹框。
- `Fresh` 表示 tokenbar 和 Total 的互斥新输入分段；request attribution 摘要可单独展示 Provider Request Input / Provider 请求输入，用于解释归因分母。
- `Tool Call` 行固定展示 tool name、command preview、result preview、timestamp、duration、result token estimate、`Result` action；duration 仅使用来源明确测得的耗时，保留测量口径与精度；零是实测零，正数不足 1ms 与未知分别显示，缺测不补值。不得用 call/output 或相邻 timestamp 差、TTFT、总时长减工具工作量推算模型或工具时间；result token estimate 使用 `~<compact>`，且必须和 Result modal 中的 `result tokens` 数值一致。
- 点击 `Result` 打开的 tool result payload modal 必须在 metadata rail 和 modal subtitle 展示该 result 文本的估算 token 数，字段名固定为 `result tokens`，数值格式为 `~<compact> tokens`；该值表示该 tool result 大概率进入下一次 LLM request 的输入压力，不得标记为 provider reported。
- 同一响应声明多个 tool_use 仅表示来源分组，不表示并行；相邻时间戳不能证明执行区间重叠。
- 工具组 header 展示本地响应边界和下发工具数；动作聚焦命令/参数短预览、状态和已测耗时。模型耗时未知只在组外集中说明，不用墙钟减工具工作量推算。
- `Subagent Run` 行展示 subagent name、独立上下文 badge、status、sub-round 数、token summary 和局部 `Expand all` / `Collapse all` 控制。
- `Subagent Run` 内部的 sub-round 按 `SR<sub_round_id>` 展示；每个 sub-round summary 行必须可点击或键盘切换自身展开/折叠，并直接展示 request/response attribution 状态和入口，不再默认展开内部 LLM call card。
- `System Signal` 行展示 parser 缺省处理、payload missing、round API error、attribution error。

### LLM Call Attribution

- `Request` 打开当前调用的正文，弹框内可展开输入归因。
- Trace round row 和 subround summary 行必须提供 request attribution 入口；Payload tab 保留完整归因详情。
- 单调用行只提供一对 `Request` / `Response` 按钮；多记录分组须展开后按调用查看归因。弹框定位保留调用身份，不以 round-local 序号冒充全局调用编号。
- request attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、重建上下文预览。
- request attribution 的 topgrid 固定合并展示调用身份、请求摘要、调用信息/时间线/请求参数与覆盖率；桌面宽度下顶部三个 summary card 必须同一行展示，不得再使用左侧 metadata rail 承载这些信息。
- 请求摘要字段固定为 agent、model、source、API family、provider、call id、Request 内容分母、Fresh、Cache Read、Cache Write、Provider 请求输入、本地重建、coverage、残差；不得在归因明细底部另起 `覆盖率与不确定性` 表格。
- request attribution 不展示泛化的残差可能来源尾注；只有存在可验证、结构化来源时才应进入具体 bucket 或诊断说明。
- request attribution 的Request 内容分母固定为 `Fresh`，用于 request 用量分布、bucket percent、coverage 和 unlocated residual；`Cache Read` 与 `Cache Write` 都是 provider/broker accounting 组件，只在摘要中展示，不作为和对话消息、工具结果并列的 request 内容 bucket。
- request attribution 候选分类必须使用全局 token 归因分类树，API payload 必须为每个 bucket 输出 `agent_bucket_key`、`canonical_key`、`category_key`、`category_label`、`color_key`、`display_order`，并把 `label` 规范为全局中文 label；前端颜色和排序必须使用 canonical metadata，不得按 agent raw bucket key 自行决定。
- 全局 request token 归因分类树固定为：`当前用户输入`、`对话消息上下文`、`工具结果上下文`、`工具定义`、`MCP 工具元数据`、`运行上下文片段`、`系统/开发者指令`、`本地指令上下文`、`Agent/Subagent 提示`、`内置系统提示`、`Provider 会话状态`、`推理配置`、`运行时封装开销`、`未定位`。
- 每个 agent 只能在自己的映射规则文件中维护 raw bucket key 到全局分类的映射；旧 raw 输入键 `tool_schemas` 必须归一化为 canonical key `tool_definitions`，并使用同一个 `color_key=tool_definitions`。
- Claude Code request attribution 的 `API messages 数组` 必须按当前 LLM call 边界重建：依次使用当前 call 之前的 assistant `request_full`、assistant text/tool_use，以及当前 call 的 `request_full`，匹配到当前 call 后停止；不得把后续 round/subround 的 assistant text、tool result 或 request_full 算入当前 request。
- Claude Code request attribution 的 `tool_definitions` 表示 request 侧发送给模型的工具定义，不得从 response 侧实际调用过的 tool call 或 `tool_calls_raw` 推断。主 agent 若在 session JSONL 中存在 `agent-setting`，必须优先按 `<cwd>/.claude/agents/{agent}.md`、再按 `~/.claude/agents/{agent}.md` 读取该 agent 的显式 `tools:`；subagent 必须按父 `Agent` tool call 中解析到的 `subagent_type` 读取对应 subagent 自己的 `tools:`。找不到自定义 agent、定义文件或显式 `tools:` 时，必须使用 Claude Code 全量 builtin tool registry。
- request attribution 的 `API messages 数组` bucket 展开区必须说明它对应发送给模型的 Anthropic API `messages` 字段，并逐条展示 role、content type、tool name、token 估算和内容 preview；bucket 汇总 token 必须使用每条消息的完整 `content_token_estimate` 求和，不得用截断 preview 重新估算；当原始全文在本地日志或重建上下文中可见时，条目必须支持二次展开查看完整内容。
- request attribution 的 `内置系统提示` bucket 若从本地 transcript 捕获到可见 `<system-reminder>` 内容，必须展示脱敏 preview；若未捕获，必须展示明确的不可见/估算说明，不得空白。
- Codex request attribution 在没有 raw request body 时，必须从 rollout 开头可见的 `session_meta.base_instructions` 和 `response_item` 中 role 为 `developer` / `system` 的 message 重建 raw `instructions` bucket，序列化后统一显示为 `系统/开发者指令`。
- Codex parser 必须把 `function_call_output` / `custom_tool_call_output` 作为下一次 assistant request 的 tool output 来源，request attribution 必须将其归入 raw `tool_outputs` bucket，序列化后统一显示为 `工具结果上下文`，不得落入 unknown。
- Codex provider reported `cached_input_tokens` / Cache Read 必须只作为 request 摘要中的 `Cache Read` 与 `Provider 请求输入` accounting 信息展示；不得生成 raw `provider_cached_context` bucket，不得计入本地重建 coverage，不得和对话消息、工具结果、工具定义等 request 内容来源并列。
- Codex request attribution 在没有 raw request `tools` 数组时，必须使用 Codex builtin tool catalog 作为工具定义缺省来源，并补充本 session 观测到的额外工具；不得只按 observed tools 数量乘固定常数估算。`tool_definitions` bucket 必须展示 tool count、每个工具的 token estimate、schema/参数 preview 和完整 detail。
- Qoder request attribution 必须优先使用 call-scoped `full_messages_array` 重建 Claude-like API messages bucket；该 bucket 必须包含当前 call 边界前的 user/assistant/tool_use/tool_result 输入，并使用完整 `content_token_estimate` 求和。
- Qoder provider reported `cache_read_input_tokens` 必须只作为 request 摘要中的 `Cache Read` 与 `Provider 请求输入` accounting 信息展示；不得生成 raw `provider_cached_context` bucket，不得计入本地重建 coverage；`cache_creation_input_tokens` / Cache Write 同样只在摘要中展示，不进入 request bucket 分母。
- Qoder 未持久化完整 available tools schema 时，request attribution 必须使用 Claude-Code-like SDK 默认工具定义并补充本 session 观测到的 Qoder-only 工具；不得只按实际调用过的工具数量估算完整工具定义。
- `Response` 打开当前调用的正文，弹框内可展开输出归因。
- Trace round row 和 subround summary 行必须提供 response attribution 入口；Payload tab 保留完整归因详情。
- response attribution 内容固定包含 topgrid 元信息、用量分布、归因明细、blocks 明细、可见内容摘要。
- response attribution 的 topgrid 固定合并展示调用身份、响应摘要、归因备注与参数可得性；不得再使用左侧 metadata rail 承载这些信息。
- 响应摘要字段固定为 agent、model、source、request_id、call_id、total output、visible text、tool call、metadata、coverage、finish reason。
- response attribution 的工具 bucket 展开区必须展示 assistant response 中实际产生的 tool call / tool input，不得展示 request 侧工具定义或 input schema。
- 用量分布和归因明细必须占用 attribution modal 内容区全宽，不得被 side rail 挤压。
- attribution bucket card header 固定展示 bucket label、precision、tokens、percent、expand chevron。
- attribution modal 里动态渲染的 bucket card 必须带有与静态 payload 模板一致的可展开语义；点击 bucket header 展开/折叠详情时必须同步 `hidden`、`is-expanded` 和 `aria-expanded`。
- 打开正文弹框时按调用和方向通过 `/api/sessions/{agent}/{session_id}/attribution/...` 加载，默认折叠，不在初始 HTML 预嵌完整归因。
- attribution modal 的 bucket detail 必须是两层展开：第一层点击贡献来源 bucket 后，若存在 `details.explanation`，先以一行全宽说明文字直接展示在展开区顶部，不得把说明伪装成子分类 card；随后展示该 bucket 内部的子分类 card，所有子分类 card 必须单列排列且每个独占一行，不得在桌面宽度下排成多列；子分类 card 折叠态只展示精简摘要、来源/role/type/token 等短 meta，折叠态高度一致；第二层点击某个子分类 card 后，在该 card 内展示可得的完整原始内容或完整解释。
- 当 attribution bucket 没有结构化 `details` 但有 `summary`、`source`、`count_label` 或 `content_preview` 时，modal 必须把这些字段作为 缺省 detail 展示，不得渲染成无法展开的空行。
- attribution bucket percent 为当前弹框中参与分布 bucket 的显示占比，单个 bucket 不得超过 100%。
- bucket 展开区必须优先使用结构化 `details.items[*].full_content`、`full_content`、`content` 或 raw JSON 字段展示完整信息；provider cache hit、previous_response_id 等本地不可见正文的来源必须展示完整解释，不得伪造原文。

### Payload Modal

- Trace 内点击 `Request`、`Response` 或 `Result` 时打开 payload modal。
- modal header 固定展示 payload title、payload id、Close button。
- modal body 固定为 metadata rail 加 main content 的双栏布局。
- metadata rail 展示 kind、内容状态、size、result tokens、source、tool、tool status 中可用字段；内容状态保留原始枚举，表示正文可读性，不等同命令执行成功；`result tokens` 只在 `tool.result` / `subagent.tool.result` payload 中展示。
- main content 根据 payload kind 展示 context、response、tool result、attribution、diagnostic error。
- payload 内容缺失时 modal 不显示空白，必须展示 requested payload、metadata、possible reasons。
- modal 内必须提供 `Open in Payload tab` 操作，点击后切换到 Payload tab 并选中同一 call。

## Payload Tab

### Payload Tab 目标

- Payload tab 是持久化深度查看区，服务原始请求、原始响应、tool result、subagent payload 和 attribution 对照。
- Payload tab 不替代 Trace 的 quick modal；它用于长内容阅读、复制、跨 call 比较和从 payload 反向定位 trace step。

### Payload Layout

- Payload tab 固定为两栏 grid。
- 左侧 call selector 宽度固定为 320px，右侧 selected call detail 占剩余宽度。
- 标准桌面和宽屏保持两栏；窄屏 `< 1024px` 改为上下布局，call selector 在上，detail 在下。
- call selector 使用 sticky header，滚动区域只在左栏内部滚动。
- selected call detail header sticky 在右栏顶部，内容区域内部滚动。
- 左右两栏的滚动互不影响。
- 窄屏 `< 1024px` 时 call selector 仍必须保留内部最大高度和滚动，不得把 selected call detail 推到几屏之后。

### Call Selector

- call selector 数据来自当前 session 的 LLM call、subagent call、tool result payload。
- 列表按 trace 顺序排列，并按 round 分组。
- 分组标题格式固定为 `R<round_number> · <round summary>`。
- call item 可保留 legacy 标题 `LLM Call #<index>`、`Subagent · <name>`、`Tool Result · <tool name>`；其中 `LLM Call #` 仅是本地 normalized 逻辑记录的展示标识，不表示一次真实 provider 请求，须就近说明此边界。
- call item meta 固定展示 model、status、input token、output token、payload availability。
- call item 右侧固定展示 status badge：`available`、`partial`、`missing`、`error`。
- selector filter 固定为 `All`、`Failed`、`Missing`、`Error`。
- 默认选中第一个 failed/missing/error call；没有问题 call 时选中第一个 LLM call。
- 当前选中项必须有左侧 active bar 和背景色。

### Selected Call Detail

- detail header 固定展示 selected call title、round id、model、status、token summary、timestamp。
- detail header actions 固定为 `Copy raw`、`Open trace step`、`Copy call id`。
- detail body 固定按顺序展示 `Overview`、`Request Attribution`、`Response Attribution`、`Raw Request`、`Raw Response`、`Related Results`。
- `Overview` 展示 call id、payload id、source、precision、duration、process time、availability。
- `Request Attribution` 使用左右结构：左侧 request summary，右侧 bucket detail。
- `Response Attribution` 使用左右结构：左侧 response summary，右侧 bucket detail。
- attribution bucket 列固定为 `Bucket`、`Tokens`、`Share`、`Source`、`Precision`。
- `Bucket` 示例值：`History messages`、`Tool results`、`Current user prompt`、`System sources`、`Visible text`、`Tool call`。
- `Tokens` 示例值：`12.2k`，表示该 bucket 估算 token 数。
- `Share` 示例值：`47.8%`，表示该 bucket 在当前 request input、response output 归属总量中的比例。
- `Source` 示例值：`provider reported`、`transcript`、`local estimate`。
- `Precision` 示例值：`exact`、`estimated`、`residual`、`unavailable`。
- `Raw Request` 和 `Raw Response` 均固定包含 `Rendered`、`Raw` 分段控件。
- `Rendered` 展示结构化 block、message role、tool_use、tool_result 和 text preview。
- `Raw` 展示原始 JSON 和原始文本，使用 mono 字体和内部滚动。
- `Related Results` 展示和该 call 直接关联的 tool result、subagent result、diagnostic payload。

### Payload Empty And Error States

- 当前 session 没有 call 时，call selector 显示 `No payload-capable calls`，右侧展示回到 Trace 的操作。
- selected call 缺少 request payload 时，`Raw Request` 显示 unavailable reason、source、precision。
- selected call 缺少 response payload 时，`Raw Response` 显示 unavailable reason、source、precision。
- attribution 构建失败时，对应 attribution 区块展示 error type、message、缺省处理、source，不隐藏区块。
- payload 内容超过 1000 行时，默认折叠到前 200 行，`Raw` 区顶部展示 `Show full raw`。

## Trace Tab 交互逻辑

### Trace 默认状态

- 页面进入时默认打开 Trace tab。
- 默认展开第一个 failed round；没有 failed round 时展开 R1。
- URL 中存在 `round=<round_number>` 时，优先展开该 round 并滚动到可视区域顶部。
- URL 中同时存在 `subagent=<subagent_id>` 时，必须在展开父 round 后滚动到对应嵌套 subagent block；若同时存在 `subagentround=<sub_round_id>`，必须滚动到该 subagent 内部的 `SR<sub_round_id>`。
- URL 深链命中 subagent 或 subagent round 时，必须自动展开对应 subagent block 和目标 sub-round。
- Trace filter 默认值为 `All`。

### Trace 操作

- 点击 round header 和 round row 任意非按钮区域切换展开状态。
- 点击 row 内按钮只执行按钮动作，不触发 round toggle。
- 点击 `Expand all` 展开所有 round，并把按钮文案切换为 `Collapse all`。
- 点击 `Collapse all` 收起所有 round，再恢复默认展开规则。
- 点击 subagent header 右侧的 `Expand all` / `Collapse all` 只切换当前 subagent 的所有 sub-round，不影响其他 round 或其他 subagent；点击单个 `SRx` summary 只切换该 sub-round。
- 选择 `Failed` 后只显示 failed round 和含失败信号的 round。
- status filter、展开状态、选中 round 必须写入 URL 参数。
- 键盘 focus 到 round row 后按 Enter 切换展开状态。
- payload modal 打开时，Esc 关闭 modal；modal 关闭后 focus 回到触发按钮。
- lazy-loaded round detail 请求失败时，expanded detail 行展示 retry 操作，不折叠当前 round。

### Trace 到 Payload

- 点击 `Open in Payload` 切换到 Payload tab，并选中同一 call。
- 点击 payload modal 内 `Open in Payload tab` 执行同一跳转逻辑。
- Trace 跳转到 Payload 时，Payload URL 参数固定写入 `payload_call_id=<call_id>`。

## Payload Tab 交互逻辑

### Payload 默认状态

- 直接打开 Payload tab 时，默认选中 URL 中 `payload_call_id` 对应的 call。
- URL 中没有 `payload_call_id` 时，默认选中第一个 failed/missing/error call。
- 没有问题 call 时，默认选中第一个 LLM call。
- 没有 payload-capable call 时，右侧展示空态。

### Payload 操作

- 点击 call selector item 更新右侧 detail，并写入 `payload_call_id` URL 参数。
- 点击 `All / Failed / Missing / Error` 更新 selector 可见项，并写入 `payload_filter` URL 参数。
- `Copy raw` 复制当前 selected call 的 raw request 和 raw response 合并文本。
- `Copy call id` 复制当前 selected call id。
- `Open trace step` 切换到 Trace tab，展开对应 round，并滚动到对应 step card。
- 点击 attribution bucket header 展开该 bucket；再次点击收起。
- 动态 bucket 内容加载中显示 inline loading，失败时展示错误摘要和 retry。
- `Rendered` 和 `Raw` 分段控件只影响当前 raw section，不影响另一个 raw section。
- `Show full raw` 展开当前 raw section 的完整内容，并保持内部滚动位置。
- Payload tab 切回 Trace 后，Payload 的 selected call 状态保留在 URL 参数中。

## 数据口径

- Created、Updated 使用源 timestamp；Wall Duration、Task Active 使用 `common.md` 的 typed timing 口径。
- Rounds 使用当前 session 的 assistant round 计数。
- legacy `LLM Calls` 仅汇总主 agent 和 subagent 的本地 normalized 逻辑记录数，须就近标明“本地记录”，不得将 records 相加宣称真实 provider 请求总量；只有来源边界证据充分时才另显示对应已确认边界计数及覆盖。
- Tool Calls 使用 tool call 计数；Failed Tools 使用失败 tool result 计数。
- Subagent Runs 使用独立 subagent 上下文启动次数。
- Output 来自模型可见输出 token，不把 hidden reasoning token 混入可见输出。
- Trace、Payload、payload modal 内的 token 值必须共享同一 usage source。
- 不同来源数据产生差异时，必须展示 source、precision、缺省原因。
- view model 必须提供统一分析对象：`run_health`、`tool_impact`、`agent_breakdown`、`agent_timelines`、`context_budget`；Token Driver 仅作为 `Agents Breakdown` tooltip、`Agents Breakdown` 行信息和 `Tool Impact` 的内部派生来源，不再映射为独立卡片。
- 失败信号必须统一汇总 round、tool_calls、subagent_runs、payload selector item、attribution errors，并反向驱动 Hero 状态、Issues 表和 Trace Failed filter。

## 状态

- session 数据不可用：展示错误状态和 `Back to Sessions`。
- 无 round：Trace 显示空态和可执行下一步。
- call 没有 raw request：`Raw Request` 显示 unavailable 原因、precision、source。
- call 没有 raw response：`Raw Response` 显示 unavailable 原因、precision、source。
- attribution 构建失败：显示错误摘要、缺省处理 和来源，不隐藏该区块。
- payload 太长：默认 preview，提供 `Show full raw` 和 `Copy raw`。
- payload API 返回 500：modal 和 Payload tab 展示错误状态并保留当前来源的 retry 操作；准确结果/输入视图不默认堆叠内部 ID，重试不能借新范围读取旧入口。

## 禁止项

- 不存在独立 Attribution tab。
- 不存在独立 Insights tab。
- 不在页面中展示 All Sessions 表格。
- 不展示 Selected LLM calls、Round diagnostics、sidecar filter。
- 不恢复 Round Map、Inspector 默认三栏、Map/Inspector/Focus 模式按钮、Density toggle、无效占位按钮。
- 不把 Trace 默认形态改成纯卡片列表；纯卡片列表只用于 round 展开后的 step detail。

### TASK-56 内容证据与展开规则

- 本地流式内容与独立导入的已物化制品使用相同短预览规则：优先本轮可见用户输入，其次工具计数及短操作，最后助手文本。catalog/sequence 引用同样提供摘要与源时间；历史用户引用只归属首次出现的轮次，不因导入入口退化为重复工具名。
- Session File 显示加载中、已提供路径、来源未提供及加载失败；仅允许的本地详情展示冻结 source file 元数据，不猜路径，不探测原文件；导入详情不泄露个人路径。
- Context Budget 未提供可验证分解时标明不可用；Tool Impact 可从归一化执行显示次数/失败次数，未测量结果 token 显示 N/A，不补零。Issues & Repro Seeds 尚未分析时不显示 `0 issues`；实际分析为空与加载失败分别展示。
- 独立助手文本、真正无正文的独立调用、不同工具执行和子 Agent 可单列 timeline-item。纯工具响应仅复述工具名的 `TOOLS` 概览不得与工具执行重复单列；多成员调用的 Request/Response 操作附着首个对应工具行，保留稳定 call ID。
- 工具类别筛选复用 `ui-select` / `ui-select__control`。右侧顺序为状态、时间/耗时、归属、token、操作；用标签区分时间点与执行时长，缺失明确显示。
- 工具行的 `Input / Result` 展开项独立按需读取正文，桌面左右双栏，700px 以下单栏；Tool Input 是命令/参数，Tool Result 是执行输出，不是模型 Response。模型 Response 可包含该调用声明的工具指令列表；后续模型 Request 消费结果不表示重新执行。
- 有工具且未观察失败、已测工具数为零、没有上下文计量项时，原状态卡主标题显示“无可用工具时长”，而非零失败计数；保留未观察失败不证明成功/完整的正文，以及不能按耗时判断慢项、查看下方操作与结果的指引。真实失败、无工具、合法零时长、已有时长但不可可信累计或非空计量项仍走原分支，不新增卡片、改变计量或请求。
- 仅当响应记录明确 `response === true`、`toolCount === 0` 且 `outputAvailable === false` 时，组头用“本地未记录工具声明”而非“下发 0 个工具”，不把本地没有声明记录说成完整输出确定无工具。已知本地输出的零工具、正数批次和非响应组保持原呈现；缺省标识不当明确缺失，不改计数、工具行、耗时、归属或请求。
- 完整正常来源中，有生产 occurrence 证据且唯一 execution 身份/scope/完整 subagent 可核的独立工具，即使模型 owner 未确认，也应在原命令位置显示安全预览并按需读取 Input/Result；“来源未确认/未观察模型输出”仍保留，不能误报参数未记录或补造调用/response refs/同参累计资格。资格与预算遵循 `session-content` 的独立 Input 条款；无证 raw 目录、冲突、截断、超限仍保守缺失，孤立导入拒绝不变。不新增面板或默认请求。
- 单页全量成员不渲染分页提示；实际分页显示 `调用记录 · 已显示 N / M` 和 Load more/Retry，加载完成仍保留已分页总数。
- 延续请求保留 generation 检查。HTTP 500 缺 header 显示真实 HTTP 加载错误并允许 Retry；409 或真实不同 generation 阻断合并并提供 Refresh page。成功但缺 generation 不视作可信快照，不插入内容。


## TASK-57 信息取舍与入口

默认保留 Total Tokens（总量）、Cache Health（输入复用）、Workload（记录/工具体量），三者回答不同问题。Run Health 不是完成证明，且重复 Hero 问题摘要；与非 Token 核心的 typed timing 一同按需展开，仍保留精度/覆盖边界。Tool Impact 默认收起以减少 top 5 与 Workload 的重复，有需要再看工具明细和本地结果估算。Issues 只有实际线索时展开；未测量、已分析为空、加载失败继续分离，定位/复制不删除。Agents 和 Context 常驻，支持从构成下钻而非堆叠更多指标卡。

共享弹框实际入口：Sessions Token bar；Projects 与 Project Detail 的 Token Cell；Dashboard Token 趋势；Session Detail 的 Agent 候选、Agent Round 柱、Trace Round bar、延迟加载的主/子 call（导入复用）。统一 `token-provenance.js/css` 色标/类型、数量/来源、占比列；列表可明确显示估算近似占比，Round/Trace 和 Dashboard 保留 provider-only 限制。Dashboard 的时间窗口占比单列说明，不与桶内构成分母混用。Project trend 目前只有来源 disclosure，没有已有四段悬浮入口，不虚构一个。缓存健康/消息数等其他图不属于四段总量构成，保留各自口径。

## TASK-82 协作阅读与过程范围

- 执行判断之后、紧凑过程之前显示同一冻结范围的 `Agent 协作`。默认至多5条委派与5个参与者投影；两层概览优先已包含可达过程的上下文（不是时间排序），深层从参与者/支路进入。过程依据可以是已确认 call，也可以是明确工具 scope/完整执行实例；不以模型 call 缺失否认已有工具过程，不表示完整采集或已完成。spawn 目标、候选 raw、catalog、观测或 unknown owner 本身不构成此依据。没有协作事实只显示简短能力说明，不造空树或按姓名/时间猜关系。
- 关系句用文字明确 `谁 → 委派给 → 谁`，就近保留安全任务短摘要、`#N / tool` 发起、任务 Input、响应/工具定位、child 过程与相关往来。匿名上下文、未找到 child、单文件未包含、冲突和资源截断分别披露；来源及完整身份按需展开，不无限右缩进。
- 委派工具返回（创建/目标 ID 证据）、等待工具本次目标报告、child 自身回答、结果后续输入关联互不替代；receiver 未确认不画 child→parent 投递边，不以报告状态推断永久生命周期或任务成功。相关往来默认20条/页，上限100；仅分页摘要，正文继续按需读取。
- 过程按完整 `agent_context` 在后端筛选全部冻结内容，诊断同步限定上下文；明确工具上下文即使没有模型 call 也须可读，不以 owner Map 缺失把它筛成空过程，模型来源仍标未知，不补 call/owner 或放宽累计资格。MAIN 工具的目标 id 不作执行者，未知/匿名/与已知 call 冲突的身份不获新资格。未加载工具/响应用稳定 target 直达，不扫描客户端前缀。保留返回全部过程、所选支路及焦点。父等待与 child 执行不相加为墙钟、模型时间或并行图。
- 协作首载在原资源批次成功并确定 generation 后发送；成功重刷同步重载。游标绑定 scope/generation/view/selection/limit，旧200/409/500不得覆盖新选择，当前500可Retry、409需Refresh。normal/import分别使用自己的 `api_base`；不读邻居补导入关系。
- 摘要仅解析当前有界页工具的明确 prompt/message/description 字段；每参数≤65536字符、每页解析/脱敏预算262144字符、每任务≤180字符，超界或未知回退任务原文入口。紧凑 join 随调用/参与者数量增长，冻结内容按单元流读；不宣称正文读取或整个投影为常数内存。离线 HTML/MHTML 维持完整静态原文及原有定位限制，不承诺在线协作交互已离线可用。

### 协作概览与所选过程的阅读层级

- 明确Codex namespace=multi_agent_v1/name=send_input的追加输入作为独立input往来，不增加父创建边、委派数或重复Agent；message及合法items保留事实，安全内容摘要不可解析不丢身份，默认不铺JSON。声明与工具回执独立保序，不配成创建回执或child回答；排队接受不证明收到/采用/完成，interrupt与submission_id留原Input/Result按需看，当前页无回执不等于全范围缺结果。不从裸名、其他namespace、正文或宿主followup_task猜协议。
- Page.inputDeclarationTotal计同一冻结source/import全范围input声明，不受selection/view/前缀影响，与“全部协作往来”实际去向一致；非零时原按钮明示“含追加输入声明N条”，无此事实保持原字样，不新增默认请求或图。只有input而无delegate时，空创建树指导不能谎称没有往来。第一次有界页不保证包含追加输入，仍手动续页，不冒称声明数为送达数、卡数或完整通信史。
- 明确`input/result_report/explicit_error`另以原执行判断近邻的一条紧凑提示呈现：“全冻结范围已记录N条明确追加输入提交错误”，不是工具失败数或所选Agent/整个任务失败。原collaboration响应携带`inputSubmissionErrorReportTotal`及至多首错`{cursor,exchangeOffset}`；计事实不双计声明、不计queued，不因未知/未采集推错，保留截断/解析限制，不增加默认API或原文。摘要与当前DOM来源状态分离，同代切支路/参与者失败不撤已知事实，换scope/generation撤旧ref。
- 错误入口一次读取同generation的`exchanges/空selection/limit20/evidence_window=input_submission_error`保护页；响应`evidenceWindow`、offset及首项明确错误均确认后才聚焦，直接到事实而非让用户翻前缀，不预取到末页。显示实际已载起点–终点/总数和未载前段，手动续页保marker/起点；切普通支路退出。整窗及嵌套reports按后端`toolPayloadState`仅为唯一工具开放按需Input/Result，不提供旧裸tool/call execution定位；歧义仍展示精确错误及原始身份，说明原文无法唯一定位。工具级Result可含全部已记录结果，不称单回执正文或child回答；未知owner/未采集目标不自动禁用唯一工具原文，不宣称全局旧入口已修。
- 注意slot不被诊断/过程重绘销毁，迟到更新不夺焦并保宽屏阅读位置；用户主动进入后如有更后操作，不再抢旧焦点。仅返回同代connected原入口，Retry不取代来源，原协作/热点返回独立。初次加载/失败/字段缺失不显示零或成功，409刷新与普通失败重试沿用现生命周期，390/1440/1920自然折行，离线能力不扩大。
- 追加输入行复用原方向、记录/工具、180字符安全摘要与按需来源/原文，内容标签为“追加内容”，不是初始任务；没有安全文本时明确摘要未解析。delegate/input/wait及未知kind须显式文案分支，未知类型中性兜底，不再把非delegate都叫等待。原创建配对、来源桥接、稳定定位、scope/generation/导入隔离和有效焦点不变，1440/390自然折行；不按消息时序分配任务成本或扩大离线取数承诺。

- 统一耗时线索的累计项按真实 DOM 顺序优先“查看上下文过程”，再“定位代表调用”，最后为可用的“查看任务与往来”；单次项仍先“定位此动作”、再任务入口。沿用现有文字、样式、请求与落点，不用 CSS order 改变视觉而保留旧 Tab 次序。累计的上下文入口仍先反馈近邻计量，再由既有链接进入有界过程，不声称一次读全调用或减少点击数。

- 协作API没有响应边界类型时，组标题、来源桥接及记录定位用中性的“发起记录 #N”；不从过程当前页猜类型或为显示预取。沿用完整actor/call/tool/target身份关联，不改变同一记录内多个委派的分组和独立工具入口。

- 默认关系保留方向、任务、发起序号、采集/未知异常和报告概况；创建/目标 ID 返回与等待本次报告分别命名，不表示 child 回答或接收确认。进入已包含的可达过程是关系与参与者的主动作；只有工具过程时同样提供，不能写成“未包含过程”，不新增 child 独立 Session 路由。原 call/明确目标编号前缀保持，新增执行上下文按来源顺序追加，不为存在性重编号。当前窗口确认有下游时突出支路，其他支路与完整往来仍在按需证据中可达。
- 每关系的原生“原文、定位与完整协作证据”默认关闭，包含 Input、Result、响应/工具定位、逐条报告与完整身份。展开不预取原文，原文仍点击后读取；完整证据比原平铺多一次展开，换取默认概览更紧凑，不宣称所有操作点击都减少。
- 所选上下文的往来中，仅当前页相邻、完整actor/call/tool/target一致且身份/依据明确、配对唯一、无父关系问题的委派声明与创建回执可合为一个任务主卡；回执类型、身份、来源、Result和定位进入既有证据区，不增嵌套展开。默认仍见任务方向、摘要、过程及创建归属简述；原两条事实仍计两条，分页不按卡数。等待/状态报告独立保序，缺失、冲突、重复、交错和跨页不拼组；不靠target聚合的报告预览配对，不把创建回执当child回答/完成，也不增请求或任务到发起记录的步骤。
- “过程与耗时”聚焦现有、带所选 Agent 标签的执行判断，同口径累计、覆盖和未知在落点可见；“直接查看所选过程”链接到过程上下文。没有复制计量卡或从当前页累加；父等待与 child 执行仍分开。
- 所选协作 breadcrumb 优先复用同完整 key 的现有权威 Agent 标签，与关系卡/诊断一致；完整 key 保留在原“采集与关联原因”折叠证据，390px/桌面键盘与指针均可核对，不只靠 hover。主上下文沿用权威主标签，未知完整兜底、不猜编号或省略尾号；导入标签不代表外部 child 已采集。迟到只同步内部文本，不替换获焦 breadcrumb 或重置 selection/分页/展开/计量，换代撤旧label，不跨正常/导入借缓存，不增面板/请求/离线承诺。
- 所选 `delegations` 仅表示该上下文作为发起者向外委派，现有参与者/关系入口、所选 breadcrumb 与空态一致说明“发起的委派”，不与委派给它的任务混淆；全范围保持中性。没有出向记录只能说“未记录”，不能说它未被委派、没有工作或未运行；可从既有协作往来核对任务、输入或报告。全会话追加输入总量不能证明当前所选上下文已有追加输入。保 actor/target 过滤、完整身份、事实/计量、请求、焦点/返回及离线能力边界，不新增面板；正常/导入两宽可读。
- 来源计时卡在现入口及原卡内使用“主会话任务活动时间／来源记录时间跨度／主会话轮次累计／来源模型计时／来源工具计时”的中文可见与可访问名称，原详情为“计时口径与来源”。详情按实际 basis 解释任务窗口（重叠只计一次）及轮次 duration／无可用窗口的主任务时长累计，不混称实测轮次；任务含工具/等待非模型，来源工具计时不同于逐工具执行器观测累计，记录跨度非持续工作、窗口外跨度非用户等待。任务计数是计时记录结束/未闭合/中止，不代表业务成功；N/A未知非零、Partial部分测量，不相减推模型或混加。保原数值/格式/计量/同卡 data 身份及按需层级，正常/导入两宽可读；O13原焦点/视口/迟到/child范围/请求保持，prepareTable/列表/排序及离线能力不扩。
- 计时说明只在原详情内按“计时口径／来源依据／缺测与记录”三个原生段落组织：分别查对象区别、实际条件 basis 与任务外跨度、未知/Partial 与任务计时记录计数。文案与条件保持单一语义来源，不丢原限制、不增加默认文字/面板/二级折叠或样式；重复更新不堆段落或残留旧依据，原 details/summary、展开与有效焦点及零额外请求保持，两宽自然断行。
- 任务窗口 basis 明确称“任务汇总方法”，说明按主任务窗口计时且重叠只计一次，不把方法标识说成本次已有可用时长或原始窗口记录。即使任务值为 N/A，已知方法仍可说明；合法0、Partial、未知/非法值及未知basis各自保持原资格、数值、来源限制和三段结构，不用basis推模型耗时或任务是否发生。
- 默认失败卡在首个失败命令近邻显示该工具已有的执行上下文，使用同一完整身份与跨区域标签；权威编号未到时保留完整身份，匿名/缺失不猜主会话。迟到标签只同步身份文本，不改变数量、命令、定位或焦点；不能按相邻主会话计量块推断失败归属，也不把父等待报告当作子工具成功。
- 失败卡原一句就近显示同一后端判定派生的安全依据：有效非零退出码、明确执行器 failed/error/cancelled，或工具结果记录含失败线索；不复制任意错误原文/路径，不在前端重判、不当唯一根因或整任务结论。退出码按 observation 非空优先；0/completed不抵消另有负面记录，cancelled不称error。有限依据缺失或非法时中性指路，正向有据场景不得用fallback替代；保数量、首工具target/命令/归属、原node/focus、请求及分页/换代隔离。本段不承诺新依据的离线导出展示已验。
- 仅失败数>0、已测工具数>0且已有可信workload卡时，将默认完整计量说明移入现有“计量说明”，不折叠失败卡或原计量卡；默认仍保已测/总量、未参与比较和实际组截断、模型未测、累计非墙钟/关键路径、未知非零、工具返回非整任务完成及“日志未明确记录时，异步任务状态未知”。完整混口径总和与限制、wait/poll例举及状态展开解释须在原生默认关闭的说明中一次键盘展开可读，计量值/来源限制/具体依据/归属/命令/target/节点/focus/请求不变。compact、无时长、零工具、无可信卡及条件外分支保持原指导，不将未知写成0；新文本离线效果本段未验。
- 有工具、无失败且没有任何可用工具时长与计量分块时，现有默认说明先回答“不能按耗时判断慢项，先看操作与结果证据”；就近保留已测/总数、未纳入比较数量、模型未测、未知不是零、工具返回不等于任务完成。完整计量和异步状态限制保留在既有“计量说明”，不新增面板或来源特例；失败、可信计量、无工具及其他未确认计量分支保持原指导。
- 可信统一线索已实际显示、全部 Agent 范围、零工具失败且有多个身份明确的上下文/口径块时，原逐块计量放入默认关闭的原生“上下文计量明细”，显示已载/总计量组数及非排名，仅截断时称前缀；一次展开访问全部原已载内容，组数不是 Agent 数。全范围覆盖、非零排除/局部缺测及完整归属、前八截断和共同测量边界仍默认可见。已载非exec_command工具或不同计时kind还须默认保留紧凑次级行，含上下文、工具名、已测累计、覆盖与非零缺口；不能仅留名称并收起已知时长，不与exec候选混排/跨家族求和，不以代表动作source断言整组家族，也不声称列出了全部未比较来源。无候选/未截断且不符合下一条窄例外/单块/失败/未知身份/无工具时长/所选Agent保持原默认呈现。明细与计量说明同级；同范围同generation追加和迟到更新保留有效节点/展开/焦点，显式范围换代重新初始化，有效来源返回先揭示关闭的祖先details；不改计量/请求或新增导航历史。
- 默认计量分组超过有界上限时，在失败之后、完整累计分块之前提供一个“耗时线索”区，只接受确定身份的 `exec_command / executor_reported / codex:exec_command_end` 观测。默认展示完整范围内已测累计最多的至多3组，每行保留上下文、已测累计、已测/同名总次数、最长单次、非零缺测/其他口径、代表动作及其定位和上下文入口。一个组的身份边界必须全部确认，但计时可部分覆盖：199/200次已测99.5s不因缺一条而整组消失，未知不补零。默认说明只比较已测子集，缺测可改变真实总量顺序，记录内覆盖不等于采集完整；全范围覆盖、身份排除、合格组数分别披露，不把组数称Agent数。
- 未截断时，仅全部Agent、零失败、原计量身份均明确且实际可信候选涉及至少两个不同完整上下文，也复用同一统一线索与上述明细分层，使重点不受主→子原分块顺序遮挡；不按合格组数/同上下文多工具推定资格，不新增算法、榜或请求。单次最大值及完整执行身份仍默认摘要可见，一次指标切换展示原单次前三条并反向保留累计最大值/身份/覆盖摘要；同时只显示一个最多3条的活动列表，不平铺6条或混合评分。无累计候选直接回退单次，无某指标不造空入口，不满足窄例外的未截断范围不添重复层。切换不发请求、不改变Agent/过程/关系范围，保留按钮焦点；过程续页/定位保留指标，Agent或冻结范围改变后重选默认，迟到身份仅局部同步。两种线索均非任务成本、效率、墙钟或关键路径榜，父等待及其他家族不混入；原完整累计和静态全文保留，不承诺未经验证的离线切换。
- 统一耗时线索在累计/单次两种列表为确定子上下文提供“查看任务与往来”，用完整身份复用既有 `exchanges` 有界页，不必先全量补关系或记编号；默认不加请求，每次显式激活最多一页，续页仍手动。与代表调用、上下文过程入口区分，不常驻复制任务长文；主上下文/匿名/冲突不猜定向目标。往来可能同时含发起和收到的记录，保留多来源与任务安全摘要，不保证第一页必有委派，也不称唯一父任务或将累计归某次任务。加载/失败范围明确，Retry/迟到结果不串选择，完成后只在未被更后操作覆盖时引导协作范围焦点；不自动读取原文或全部参与者。
- 从耗时热点打开任务往来后，协作区提供“返回耗时位置”，仅恢复仍有效的原热点按钮的焦点与可见位置，不增加请求；与“返回协作位置”的来源独立。指标切换或节点替换导致原入口失效时撤销该返回，不猜替代节点、不承诺跨重建历史；重试保留有效热点来源而非临时Retry按钮，迟到响应不抢后续焦点。390px与桌面自然换行，离线档案不新增交互承诺。
- 过程旁无真实来源历史时用“查看 Agent 协作”聚焦当前可用概览；从有效委派/参与者/往来入口进入后用“返回协作位置”聚焦原入口，不把查看概览命名为返回支路。来源节点失效或快照换代时撤销旧返回含义，按现有概览降级或隐藏；无协作位置时不显示空导航，普通追加与局部标签同步保留有效来源。导航不新增请求或改变过程范围。
- 若选择过程仍在读取时用户已返回，随后到达的数据可正常填充，但不得把焦点又抢回诊断区；取消的是过期的自动聚焦意图，不是数据或范围。
- 已存在工具 Result 但 available 正文为空时，提示“已记录工具返回，暂无可展示的非空正文”；不猜测空串/null/缺 output 字段。真正缺失 Result 保持缺失提示，结构化记录中明确空 output 的既有展示与复制不变。


### 相同参数记录的重复调用耗时

- 目的：当一个Agent包含多种重复调用时，在原累计项内指出哪一份参数记录的已测累计最多，而不是仅靠单次最长命令猜整组耗时。不新增同层榜、状态面板或默认请求，不替换原最长代表及其定位。
- 分组严格比较当前完整规范化参数记录String；参数记录不同，即使脱敏/180字预览相同也不合并，不按脚本名或语义猜分类。既有来源可能将结构化参数与原文本归一为相同记录，不声称原wire字节/类型相同、同业务任务或同环境。
- 仅明确Codex来源、已确认完整执行上下文和当前可信exec_command测量家族、父组全部输入可识别且至少两种记录、最高已测累计组本身至少重复两次可信测量时显示；单输入/全唯一/冲突/不完整/预算超限不添空态。输入识别资格与时长覆盖分开，未知不是零，其他口径不混入；原覆盖/模型未测/来源仍可见。
- 1440/390在原100s/200次项内先读“其中：参数记录相同的调用已测累计最多90s · 已测180/180次”，再读安全beta摘要与本组2种参数记录；原alpha最长500ms和35s单次最大不变。输入100%识别是资格不变量，200/200详细适用计数放既有计量说明，不默认堆三个分母；partial保持179/180及非零缺测/其他口径。新90s包含于100s，不可相加，也不绑定某次委派或某一次beta。
- 仅累计活动项消费新事实，单次metric不另铺输入累计；所选Agent原近邻累计通过完整上下文/工具和可信计时集合一致性复用同一事实，不多一次展开、不扩旧显示门槛。参数输入/工具证据仍按需，不偷换原最长代表定位。
- 数据来自完整冻结范围，不随过程20/40条或续页改变；Agent/范围/generation隔离、指标最后意图/迟到标签、原完整来源与返回焦点不变。只承接安全投影文本，不据此声称HTML/MHTML离线交互已验证。

- 同参数热点行在摘要之后最多提供一个“定位此参数的一次调用”入口，复用实际服务端样例工具身份和既有定位/有界目标页，不从预览猜ID、不先20→40续页、不自动切Agent、不并入原三个同层按钮。仅显式点击读过程摘要，不自动展开证据/原文；样例不代表90s单次或核验180次。原alpha定位、当前指标、键盘工具聚焦、更后意图优先、真实协作返回与失效降级保持；无资格/单次不出现空入口。自然折行，默认仍零新增请求，不扩大导出/离线能力。

### 热点上下文名称与权威身份

- 默认可见的耗时热点与过程上下文，在有完整call依据时直接使用同冻结范围协作目录的Agent标签，不要求用户先加载参与者或手动比对长ID。名称只用于阅读，完整context key仍是唯一身份，不改变计量、排序、任务归属和定位tuple。
- 标签随当前冻结内容的完整遍历口径生成，不按子Agent ID尾数、热点次序或所选局部范围猜编号；同代已载协作标签优先，换代清旧标签后接纳当前有效提示。没有权威提示时保留完整身份兜底，不假称同一Agent。
- 只在既有execution响应携带当前有界过程/诊断实际引用的显示提示，不新增默认请求、参与者预取/自动翻页或全目录，也不新增内容扫描。单文件导入只有主上下文时保留主会话文案，不从其它session/import借标签。迟到提示只更新文本，保留有效节点、展开状态、焦点和既有返回上下文。

### 宽屏联合排查

- 至少1600px且已有可确认协作事实时，左侧连续呈现执行判断、原主会话计时入口和执行过程，右侧保留唯一的现有协作组件及其状态；Token/完整证据分析仍在两栏下方全宽。短 Agent 过程不被全局协作隔开或拉伸。
- 右栏紧邻标题说明“独立展示当前协作范围，不与左侧逐行对应；范围见下方导航”。保留原范围、委派顺序和手动分页，不把最大耗时 Agent 自动搬到第一条，不以空间邻接暗示任务成本、时间对应或因果。
- 1600px临界处单工具命令仍自然可读；操作组可换行，不缩字号、截断或藏证据。1599px、1440px、390px保持原单列顺序；加载占位和无确认关联不占空右栏。无sticky、固定高度、区域内滚动或新请求。
- 迟到协作、手动续页和宽度变化保留有效原生展开、焦点及阅读位置；耗时→任务与协作→过程各自返回原有效入口，Payload切换真正隐藏Trace。仅改变在线布局，不扩大离线能力承诺。

### 结果与后续本地输入的阅读链

- 单条准确模型输入（main:req / sa:req）首层依次为可读输入正文、本条记录中的工具结果；没有单列正文但有工具结果不称空输入。输入归因和原始记录仍可展开，展示的本地记录不等于提供方真实请求次数或完整上下文。
- 整轮聚合Request保持现有全文/归因路径与逐调用查看指引，不冒充单条输入，不请求仅支持准确记录的结果关系视图；无模型调用的原输入仍可读。
- 工具Result按独立来源结果分项，不从合并全文拆段或按相同文字关联。同响应直接显示每项的准确本地输入预览，例如R1→本地记录#2、R2→#3；前20项各最多一个预览，未加载、还有后续、完整无引用与不能确认分别说明。一个结果多个输入、同输入重复引用均可手动继续查。
- 若无法单列结果但工具级记录仍有安全正文，首层展示“未分项的工具输出/全文”，明确包含关系未确认；不要求再展开才读到已有内容，不从raw造结果或关系。原工具级审查/Copy入口保留。
- 点击目标在同一modal直接定位准确输入引用，即使在后续窗口；返回恢复原结果项/页/展开/内滚动/按钮焦点，关闭仍回Trace原入口。输入原文与完整身份归因保当前normal/import范围，不猜轮次。
- empty、missing与真实截断分开。工具级原始全文及Copy保留尾部；已截断时首层提示，不能标为完整记录。500保已载内容并原URL重试；失效入口重读同范围原结果，换代清旧目标/返回链。迟到数据不抢更后焦点，同视图分页不取消合法归因读取。
- 默认详情不预取payload/关系，不增加7/6请求。390/1440使用相同正文→目标→边界顺序，不靠颜色或内部ID让用户比对。静态HTML/MHTML使用相同安全来源分类，仅已收录准确引用可生成原生片段；不把静态档案说成在线modal或保证MHTML片段导航。
