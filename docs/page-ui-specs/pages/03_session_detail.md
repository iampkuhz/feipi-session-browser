# Session Detail 页面规约

- Token KPI、缓存比例、round/call/subagent、attribution 遵循 `common.md` 的 `Token Measurement Provenance`。session 级估算不复制到无 usage 的 call；未知输入不进入低缓存筛选或伪造 0% 折线，导入 scope 保持独立。

## 定位

Session Detail 先展示会话身份与 Token 用量，再通过唯一的「执行过程」回答：哪个轮次执行了什么、是否失败、依据在哪里。

## 页面布局

- 个人详情使用 `/sessions/<agent>/<session_id>`；导入详情复用 `session.html`。静态归档见 [Session Export Contract](../../session-export-contract.md)。
- 在线详情自上而下为会话头与指标、Token 分析、执行过程三段。会话头展示 Agent、标题以及有内容时的首问入口，不在标题旁重复首问；模型、项目、ID、文件路径折进「会话信息」。
- 四张会话指标卡和 Token 分析直接可读。桌面验收覆盖 1024 CSS px 及以上；分析区左侧为 Agent 候选表，右侧为关联图表。执行过程没有同级 tab，不重复绘制平铺工具列表。
- 执行过程以轮次为行，展开读取该轮助手回复、子 Agent、工具指令与结果；同一回复声明的工具保留归属、独立输入和结果。失败定位、筛选和翻页都作用于这张表。
- 除明确失败或可信计时外，不显示泛化的执行判断。没有失败不等于成功，未记录时长也不等于零；必要的口径放在对应数值的提示中，不重复贴免责声明。
- 原文首先从对应轮次、调用或工具查看；需要跨记录查找时才展开执行区内的原文索引。不预取所有正文或所有页。
- 静态 HTML/MHTML 保留冻结数据与原生展开操作，不模拟在线交互。

### 导入分析范围

- `/imports/<import_id>` 复用单一执行过程、Token 摘要及原文/归因下钻，不为导入改变主视图结构；完整入口行为见 `09_imports.md`。
- 导入详情面包屑为 `导入分析 / <filename>`，主导航高亮导入分析。
- Hero 前常驻“仅分析此文件，不计入个人统计。”，并提供“导入另一个文件”“返回个人 Sessions”；范围提示不能被异步 metadata 加载替换。
- 范围提示仅显示一次，不在 Token 卡上重复。
- 所有 round/payload/attribution/bucket-detail 请求均来自 `/api/imports/<import_id>`；原来源 session ID 不能导致回落个人 API。
- 导入详情不暴露服务器临时路径，不提供会错误访问个人同 ID 会话的导出按钮；个人详情与离线导出行为保持。

## 文字内容

- 同一页自上而下阅读，不提供标签栏。列表完全载入时不显示分页提醒；部分载入时给出范围和操作。
- Hero 的四张原生指标卡分别呈现 Token 总量、输入端缓存命中率、本地记录工作量和耗时。
- Hero 本地文件路径行 label 固定为 `Session file`，展示索引或解析阶段定位到的本地 JSONL 绝对路径；路径缺失时不渲染该行。
- Hero 本地文件路径行必须提供 `Copy session file path` 按钮，按钮使用统一 `data-action="copy"` 和完整 `data-copy-text` 路径，供用户直接粘贴到终端或编辑器。
- 每张卡直接显示主值及多个相关子值，最多四个二级指标，不为了对齐补低价值指标。数值和必要标签不依赖点击；补充口径、分母和来源可在就近提示中查看。
- Round 标题使用 `R<round_number>` 加 summary；summary 缺失时显示 `Untitled round`。
- 原文缺失时显示 unavailable 原因、precision 和 source，不用空白区域代替。

## Hero KPI

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
- `Tool Calls` 使用全局 tool call 总数；如需展示主 agent 口径，必须与全局总数区分。
- `Subagent Runs` 表示独立 subagent 上下文启动次数。

### 耗时

- 来源任务窗口用 MAIN 源任务窗口的 union（`timing.activeTaskSeconds`），不是模型推理。任务活动、墙钟、Agent Turn workload、模型和工具的执行耗时按实际来源区分，不互为替代。
- 遵循 `common.md` 的 typed timing 精度。缺来源明确标记，不用 legacy execution、零值或跨夜 transcript span 补齐；不从墙钟减工具工作量推算模型耗时。
- 在线详情的时长用秒或分秒表达；不足一秒保留可用精度，实测零、非零和未知不能混淆。
- 会话开始时刻与耗时卡分开呈现。只有来源明确记录启动才称为启动时间；普通记录时间点不冒充启动。已测工作量并非会话墙钟，必要的来源或口径说明就近呈现。

## Token 分析

### Agents Breakdown

- `Agents Breakdown` 左为候选表、右为所选 Agent 的图表。候选表优先展示 Agent、已记录模型、本地记录、已确认调用、Token、工具与失败。文件与 ID 通过所选 Agent 的「来源 ID 与文件」获取。超过约五个候选后列表内部滚动。
- 归一化记录和有响应/累计计量边界证据的调用分别计数；未确认边界的记录不作为调用次数。会话级模型不回填进未知的 Agent 记录。
- 主 Agent 默认选中。柱图和缓存折线只使用所选 Agent 在当前 Trace 已加载轮次内的用量；混合轮按真实归属汇总。同一个轮次在图表和 Trace 使用同一 R/G 标识。
- 柱图使用共享 `TokenProvenance` 构成与来源提示，保留鼠标、键盘和跳转；折线只使用完整服务商上报输入，以 Cache Read / Input 计。

### Token 构成

- 卡片定位：解释当前 session 用量的可验证构成，而非模型 context window 占用率。
- 图表类型固定为水平分段条形图。
- 分段来自 DTO 的真实分类/纳入状态；Tool Results 是构成之外的本地估算，不塞进构成条。
- x 轴显示 token share，范围固定为 0% 到 100%。
- y 轴只有一行，标题固定为 `Session Context`。
- 分段条可在空间足够时内嵌分类名和占比；窄分段隐藏内嵌文字，但保留 tooltip。
- 图例简短，标签、数值、占比和来源就近排列；长标签可回流，桌面窗口内不溢出。顺序和色标与构成条一致。
- 不渲染配套明细表或每分类独立 progress track；细节通过 `common.md` 的 `Chart Tooltip` 展示。
- tooltip 固定展示 `Segment`、`Tokens`、`Share`、`Source`、`Precision`。
- 仅明确纳入且有可用 share 的分段参与构成；Partial 为近似、非服务商精确统计。构成条与图例仅列有正占比的已纳入项。指标卡保留实测零，未知不补 0%。缓存比率仅使用完整服务商上报输入，分母不含 Output。

## 执行过程

### 轮次导航

- 轮次表本身即执行过程，不另设轮次页。
- Trace 默认以 table 形态展示 round 列表，保证长 session 能快速扫描、排序和定位失败。
- Round 展开后使用 step card 形态展示详细过程，吸收高保真稿中可读性更好的时间线结构。
- Trace 和 Payload 使用同一 call id、round id、payload id，必须能互相定位。

### Trace Toolbar

- 说明从简；同一响应声明多个工具只表示来源分组，不表示并行。
- toolbar 右侧固定展示 status segmented control 和 expand control。
- status segmented control 候选项固定为 `All`、`Failed`、`Low cache`。
- `Low cache` 展示 round-level Cache Read ratio 小于 20.0% 的 round，用于定位 Hero `Low-cache Rounds`。
- expand control 是一个全局 toggle，文案固定在 `Expand all` 和 `Collapse all` 之间切换。
- Trace filter 状态必须写入 URL 参数 `trace_status`。

### Trace Round Table

- 六列分别展示轮次标识、摘要、本行 Token、原文入口、时间与耗时；已观察到的状态或缺口随摘要显示，不设独立信号列。
- 轮次列展示 `R<round_number>` 或分组标识以及对应的状态。
- Codex 的 `R<round_number>` 表示第 N 个有效 LLM call round，而不是第 N 个可见 assistant 文本窗口；无可见文本但有 tool_use 或 usage 的 Codex call 也必须保留为 round。
- 摘要列占剩余主宽，展示当前轮短摘要：优先可见用户输入，其次工具名称/次数与短操作预览，再回退助手文本。必须解析当前调用的 inline/catalog/sequence 引用，过滤系统上下文及工具结果；不得跨轮借文或嵌入长代码/输出。真正缺失显示 `摘要未记录`。
- 轮次计数要区分本地归一化记录数、已确认模型调用数及新声明的工具执行数；消费历史工具结果不计为新执行。
- `Token Cell` 的彩色 tokenbar 宽度必须按当前 session 最大 round token total 归一化，最大 round 为满宽，其他 round 按比例缩短；未占用的轨道使用灰色背景显示与最大 round 的差距。
- 1024px 与 1440px 桌面窗口的 Request 和 Response 分别可点击、可用键盘打开，并与相邻时间列留出间隔；没有原文不伪造入口。多记录分组从展开行按调用查看。
- 时间列展示本轮来源时间，耗时列展示有记录的本轮耗时。缺测显示 `—`（提示为「未记录」）；不借用会话更新时间、工具发起时间或相邻时间之差。
- 表头的 Token 排序按 total tokens。
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
- 每个工具的命令、发起时间、实测耗时、Input 和 Result 属于同一行组；展开工具原文时，计时和其他入口不横移。工具发起时间指来源声明时间，不冒充执行器启动时间。
- `Fresh` 表示 tokenbar 和 Total 的互斥新输入分段；request attribution 摘要可单独展示 Provider Request Input / Provider 请求输入，用于解释归因分母。
- `Tool Call` 行固定展示 tool name、command preview、result preview、timestamp、duration、result token estimate、`Result` action；duration 仅使用来源明确测得的耗时，保留测量口径与精度；零是实测零，正数不足 1ms 也不能显示为零或未知，缺测不补值。不得用 call/output 或相邻 timestamp 差、TTFT、总时长减工具工作量推算模型或工具时间。
- 同一响应声明多个 tool_use 仅表示来源分组，不表示并行；相邻时间戳不能证明执行区间重叠。
- 工具组 header 展示本地响应边界和下发工具数；动作聚焦工具类别、状态和已测耗时；摘要不复述命令。模型耗时未知只在组外集中说明，不用墙钟减工具工作量推算。
- `Subagent Run` 行展示 subagent name、独立上下文 badge、status、sub-round 数、token summary 和局部 `Expand all` / `Collapse all` 控制。
- `Subagent Run` 内部的 sub-round 按 `SR<sub_round_id>` 展示；每个 sub-round summary 行必须可点击或键盘切换自身展开/折叠，并直接展示 request/response attribution 状态和入口，不再默认展开内部 LLM call card。
- `System Signal` 行展示 parser 缺省处理、payload missing、round API error、attribution error。

### Request、Response 与 Result 弹框

- 从执行台账按轮次和调用打开原文，在弹框打开时才按方向加载载荷与计量。导航在点击前标明目标轮次/调用和 `Request`、`Response`、`Input` 或 `Result`；不以轮次内序号或工具显示名匹配工具 ID。没有对应结果记录时不提供 `Result` 入口。
- `Request` 和 `Response` 默认可见当次输入或输出总量、正文分项和未识别量。服务商报告、可见正文估算及重建分开；缺测不填零，缺正文不抹去已报告总量，分项试算超过总量时不显示占比或负余量。缓存命中、未命中用同次输入作分母、独立显示，不与正文分项相加，也不视为可节省的计费量。
- Side Chat 有来源证据的压缩调用可在没有用户原话时单独阅读；已记录输入用量时照常开放 `Request`。压缩身份已确认但推理未单列时，保留已报告总输出和未识别量，不补算压缩份额。比较压缩前后的当次输入，不使用任务累计，也不把未展开的快照当作已知差额。
- 记录来源、记录入口类型、客户端标识、CLI 版本、模型和供应商各占独立键值；正文使用整宽内容块，标字符数，长文在块内滚动。标识本次记录或历史重建，保留可访问的原始记录；本机技能仅作参考，不作为历史记录或计入 Token。缺工具定义时明示缺失，不从使用过的工具推断注册清单。
- `Response` 的每个工具项包含名称和有证据的参数（原文不可用时用已记录的预览），同一项下链接到该 ID 的 `Input`/`Result`。原始机器字段不放在工具项标题里。
- `Result` 先读该工具的命令或参数，再读返回。标题下展示声明记录的发起时间与测得的耗时；声明不是执行器启动时间，未测则显示「未记录」。返回正文以可读内容的估算总量作分母，不重复计入命令、参数或模型用量。已知所属响应时可返回该 `Response`。

## 从执行记录查看原文

- 点击模型 Request / Response 查看该调用的本地记录；工具输入和结果从「工具原文」展开。正文与归因共用弹框，不推断完整 HTTP 上下文。
- 执行区的折叠原文索引可按 Agent 查找本地记录，首次打开才请求有界索引；确认存在的方向才提供按钮。拒绝跨代续页，失效或网络错误提供恢复操作。

## 执行过程交互

### Trace 默认状态

- 默认显示轮次索引；`round` 和 `trace_status` 分别定位轮次或应用筛选。
- 默认不展开正文，明确的深链或点击才读取轮次。
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

## 数据口径

- Created、Updated 使用源 timestamp；Wall Duration、Task Active 使用 `common.md` 的 typed timing 口径。
- Rounds 使用当前 session 的 assistant round 计数。
- legacy `LLM Calls` 仅汇总主 agent 和 subagent 的本地 normalized 逻辑记录数，须就近标明“本地记录”，不得将 records 相加宣称真实 provider 请求总量；只有来源边界证据充分时才另显示对应已确认边界计数及覆盖。
- Tool Calls 使用 tool call 计数；Failed Tools 使用失败 tool result 计数。
- Subagent Runs 使用独立 subagent 上下文启动次数。
- Output 来自模型可见输出 token，不把 hidden reasoning token 混入可见输出。
- Trace、Payload、payload modal 内的 token 值必须共享同一 usage source。
- 不同来源数据产生差异时，必须展示 source、precision、缺省原因。
- Token Driver 只作为 `Agents Breakdown` 的提示或候选行附属信息，不映射为独立卡片。
- 执行过程的状态与 Failed 筛选使用已观察的失败证据。没有失败记录不等于会话成功；工具错误和缺失证据仍在关联记录中可见。

## 状态

- session 数据不可用：展示错误状态和 `Back to Sessions`。
- 无 round：Trace 显示空态和可执行下一步。
- call 没有 raw request：`Raw Request` 显示 unavailable 原因、precision、source。
- call 没有 raw response：`Raw Response` 显示 unavailable 原因、precision、source。
- attribution 构建失败：显示错误摘要、缺省处理 和来源，不隐藏该区块。
- payload 太长：默认 preview，提供 `Show full raw` 和 `Copy raw`。
- payload API 返回 500：在出错的原文入口展示错误状态与重试操作。

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
- Token 构成未提供可验证分解时标明不可用；未测量的工具结果 token 不补零。
- 独立助手文本、真正无正文的独立调用、不同工具执行和子 Agent 可单列 timeline-item。纯工具响应仅复述工具名的 `TOOLS` 概览不得与工具执行重复单列；多成员调用的 Request/Response 操作附着首个对应工具行，保留稳定 call ID。
- 工具类别筛选复用 `ui-select` / `ui-select__control`。右侧顺序为状态、时间/耗时、归属、token、操作；用标签区分时间点与执行时长，缺失明确显示。
- 工具行使用单一「工具原文」入口按需读取正文，桌面左右双栏；需要完整弹窗时可从有正文的一侧打开；Tool Input 是命令/参数，Tool Result 是执行输出，不是模型 Response。模型 Response 可包含该调用声明的工具指令列表；后续模型 Request 消费结果不表示重新执行。
- 单页全量成员不渲染分页提示；实际分页显示 `调用记录 · 已显示 N / M` 和 Load more/Retry，加载完成仍保留已分页总数。
- 延续请求保留 generation 检查。HTTP 500 缺 header 显示真实 HTTP 加载错误并允许 Retry；409 或真实不同 generation 阻断合并。个人详情若确认已发布不同代次且能从新视图验证当前阅读目标，最多自动整页恢复一次；无法确认、目标消失或连续换代时改为提示用户。成功但缺 generation 不视作可信快照，不插入内容。


## Token 构成共享入口

共享弹框实际入口：Sessions Token bar；Projects 与 Project Detail 的 Token Cell；Dashboard Token 趋势；Session Detail 的 Agent 候选、Agent Round 柱、Trace Round bar、延迟加载的主/子 call（导入复用）。统一 `token-provenance.js/css` 色标/类型、数量/来源、占比列；列表可明确显示估算近似占比，Round/Trace 和 Dashboard 保留 provider-only 限制。Dashboard 的时间窗口占比单列说明，不与桶内构成分母混用。Project trend 目前只有来源 disclosure，没有已有四段悬浮入口，不虚构一个。缓存健康/消息数等其他图不属于四段总量构成，保留各自口径。

### 桌面阅读的计量与定位

- 助手回复保留在对应轮次，不在页头重复。已测工具累计工作量和覆盖数保留来源及精度，放在执行过程内，不与会话墙钟时间混用。
- 执行过程保留首个实际失败的定位及已记录的结果。目标已加载时只定位和聚焦，未加载时追加定位片段，不替换已展示的执行记录和列表范围。
- Trace 隐去默认 `1 records`、`0 tools` 及内部分片编号；工具行保持 28px。「工具原文」集中输入和结果，原文索引对未记录的方向不提供空按钮。

### 轮次行与卡片边界

- 桌面轮次表头及摘要行统一 36px。长摘要单行省略，完整内容从标题提示或轮次原文读取。Token 数、色条和计数横排。展开详情不限制此高度。
- 页头与 KPI 的间隙沿用页面底色；白色只在卡片边界内绘制。同级卡片共用 8px 间距、12px 水平内边距和 14px 圆角。执行记录工具栏与表格共享一个边框。
