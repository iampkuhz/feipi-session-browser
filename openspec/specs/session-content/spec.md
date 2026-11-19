# Session 内容中的工具结果与执行观测

## Requirements

### Requirement: 工具结果保留独立于后续消费
当前来源到全新索引的普通与 managed 路径 SHALL 保留每条可唯一关联的实际工具结果，包括没有后续响应的尾部结果和显式空结果。结果正文与存在性 SHALL 复用当前 source-unit/catalog 内容能力，不以消费边为存在条件，不倒灌过去请求，不伪造消费调用，不增加模型响应、工具声明或 Token 计数。

#### Scenario: 尾部结果持久化与空结果
- **WHEN** 工具声明后存在明确结果，但没有后续模型记录
- **THEN** canonical 与 SQLite 关闭重开后的工具 Result SHALL 保持可读，消费关联 SHALL 为空，结果存在摘要 SHALL 为真；缺少结果的工具仍为 missing。
- **AND** 显式空结果 SHALL 为 available 且正文为空；摘要只收集稳定身份的存在信息，不为每个工具读取全文。来源、scope 和 occurrence SHALL 防止同名或同裸 ID 串绑。

#### Scenario: 声明与结果先于同一计量收口记录
- **WHEN** 同一 scope 的工具声明、工具结果先于归属该声明的 `token_count` 或 `token_usage_record` 收口记录出现
- **THEN** 该计量记录 SHALL 保留原调用、声明归属与 Token；工具结果 SHALL NOT 作为声明该工具的同一 call 的 Request 内容或消费边。只有确有后续适用模型记录时才可关联后续消费，没有后续记录时消费边 SHALL 为空，完整 Input/Result 仍保留。
- **AND** 普通与 managed 的消费边、Request source units 与独立结果存在性 SHALL 一致，不以添加调用、改源顺序、删结果或放宽 scope/owner/同输入累计资格取代因果修复。

#### Scenario: 同一工具的结果分别关联不同请求
- **WHEN** 同一 canonical 工具 T 的两条实际结果按 F1 声明 T → R1 → F2 → R2 → F3 出现，且每条结果均可按来源位置与 scope 唯一关联
- **THEN** 普通与 managed SHALL 将 R1 的 ID、正文/source units/refs 归 F2 Request，将 R2 的对应内容归 F3 Request；两个请求可各自引用 T，保持原顺序与 multiplicity，不以最终工具级单值将 R1 移至 F3。原声明 owner、Input、三 call/一 execution、Token/计量及两条独立完整 Result SHALL 保持。
- **AND** 此关联仍为本地归一化事实，不证明 provider 实际消费，不新增 DTO/schema/DB 字段或把一工具拆成多 execution。

#### Scenario: 消费摘要仅表示全部结果的一致目标
- **WHEN** 工具至少有一条已观察 Result，且全部 occurrence 均可唯一关联同一适用后续 call
- **THEN** `resultConsumedByCallId` SHALL 填该 call；两个相邻结果同归下一帧时正文顺序与重复 ID 引用 SHALL 保持。
- **AND** 无结果、任一结果无后续/EOF/不唯一，或结果分别归不同 call 时 SHALL 为空。空仅表示没有完整一致的单值摘要，不等于没有结果或从未关联消费；已知各 Request 关联与完整 catalog SHALL 不受影响，不忽略末条未关联结果而保留早期摘要。晚到 Response 与真实 user 的 O8 边界保持。

#### Scenario: 独立工具 Input 不依赖已确认模型 owner
- **WHEN** 受支持的完整正常来源记录了工具参数，但该工具没有可确认的模型响应
- **THEN** 列表与 managed 路径 SHALL 在真实分配点保留未归属 frame 的 record ordinal/tool slot，并经既有 canonical identity 在原位置发布独立 RESPONSE/tool_use 内容；其 Input SHALL 可经现有 catalog/codec、canonical 与 SQLite 重开读取。不得 zip 工具列表、按裸 ID 回搜、全量 SourceRecord 兜底或临时从原文件补命令。
- **AND** 独立内容资格 SHALL 可由生产来源位置/slot、catalog key/种类及唯一 execution 的规范化 ID、原工具名、明确 scope/完整 subagent 共同核验；artifact/stream payload 与 web preview SHALL 共用一致资格实现或同一经验证结果。无证 raw 目录、重复/冲突、伪造/非法来源、不完整/截断或超预算 SHALL 拒绝，不任选 first/last，不以已读前缀宣称唯一；跨 scope/source/import/generation 不串联。复用既有结构与预算，不新增 domain/codec 字段或通用 registry。
- **AND** 可查 Input 不证明模型 Response 存在，不补 call、owner、response refs、消费边或严格镜像，也不取得下述同完整输入累计资格；原 Result、Token、计数和计量保持。原 call-owned 路径与无证 unbound 目录拒绝保持。孤立 tool-only 导入仍为 empty_input，只有 user 而无后续 assistant 的无 owner 声明仍按 TOOL_OWNER_UNAVAILABLE/parse_failed 拒绝，不扩导入形态或旧索引兼容。
- **AND** managed writer 与 reader SHALL 将现行精确 declaredByCallId=unknown 视为缺失 owner 而非实际 call 强引用，不创建虚拟 call；其它实际 owner、resultConsumedByCallId 与 parent refs 的悬空引用及原重复/总量校验 SHALL 继续拒绝。

#### Scenario: 有内容的当前静态档案
- **WHEN** 新建普通 compact 或 managed 会话有可用内容，使用既有 HTML/MHTML 导出路由
- **THEN** 现有静态 snapshot SHALL 包含全部已发布 call/tool 正文，不受在线分页/筛选裁剪，不因 artifact 同时存在而退为元数据；使用原生 details 和片段来源链，不新增 live tabs/modal/filter。
- **AND** manifest 大小 SHALL 对应实际档案；standard 脱敏、50 MiB 超限拒绝和现有 data-bundle 合同不因路由修复改变，不增加旧索引兼容或迁移。
- **AND** HTML SHALL 支持原生工具到声明记录的片段定位。MHTML SHALL 保留相同完整正文和原生展开；档案内 SHALL 明确部分浏览器不执行 MHTML 页内跳转，需定位时优先使用 HTML 或手动展开声明记录。此浏览器限制不应被标成已修复，也不通过脚本或新框架伪装同等导航支持。

#### Scenario: 同一工具的全部实际结果可独立查看
- **WHEN** 同一 canonical 工具有多个不同来源位置的结果，分属不同模型 Request 或包含 EOF 结果
- **THEN** 工具级执行结果查看及 HTML/MHTML SHALL 保留所有实际结果的完整正文与来源顺序，不以首个内联结果或单值消费摘要截断；同一 occurrence 的内联与独立目录镜像不得重复，真实不同位置的同文本结果不得按正文去重。
- **AND** 逐次 Request、完整 Input、显式空/缺失、安全策略、计量与现有有界导出和私有索引清理保障 SHALL 不变。

### Requirement: 显式执行器观测保真
系统 SHALL 仅保留来源显式提供且可按稳定工具身份关联的执行器观测。Codex `exec_command_end` 的 `call_id`、`process_id`、`duration:{secs,nanos}`、`exit_code`、`status` SHALL 经 SourceRecord、spool、普通与 managed normalization、canonical 内容及两种 API 路径保持一致。

`observation.kind=executor_reported` SHALL 表示执行器上报耗时，不表示进程生命周期、模型耗时或墙钟占比。`observation.source` SHALL 使用不含物理路径的事件定位符。`durationNanos` SHALL 保存精确非负整数；`durationMs` 只作向下取整的毫秒摘要，未知为 null，合法零为 0。超出精确 long 纳秒范围、负数、分数、字符串或非法 nanos SHALL 保留未知并附原因，不允许截断非法输入或溢出回绕。

显式 exit/status/process SHALL 保存在 `observation`；原 `status` SHALL 继续表示结果错误信息，不把显式 `completed` 当错误，不把缺少错误当进程成功。缺失退出码及状态 SHALL 保持未知。

#### Scenario: 顺序、重复与作用域
- **WHEN** 工具结束观测出现在声明或结果之前或之后
- **THEN** 系统 SHALL 仅在相同物理来源和执行 scope 内按唯一稳定 call ID 关联，不按工具名、process ID 或时间戳关联。
- **AND** 重复观测 SHALL 不新增工具、模型响应或 result；互相矛盾的观测 SHALL 清空争议指标并保留 `conflicting_observations`，不得任选首条或末条。
- **AND** 无声明、跨 scope 或同 scope 重复裸 ID 导致归属不唯一时 SHALL 保持工具未知，不猜 occurrence。

#### Scenario: 未测量不补零
- **WHEN** 当前来源未提供支持的显式工具计时，或只在结果正文出现耗时文字
- **THEN** 工具 duration SHALL 为 null，不解析任意结果正文猜测计时，不从外层写出 timestamp 倒推起止，不以 TTFT 或相邻记录差值补模型耗时。
- **AND** 显式零、缺失、非法及冲突 SHALL 经序列化与 API 保持可区分；task-window 算法、Token 及工具/响应/result 计数 SHALL 不因观测补充而改变。

#### Scenario: 当前发行重建
- **WHEN** 发行采用当前内容契约
- **THEN** 系统 SHALL 从原始来源重扫到全新索引目录，不实现旧索引迁移、跨版本读取或兼容分支。

### Requirement: 显式多 Agent 协作证据保真
系统 SHALL 从当前源的明确字段保留委派、等待及对应结果报告，使用带来源与 scope 的完整实例和工具身份。每个工具可以关联多个目标事实；声明调用决定执行者，工具关联的 child ID 不得冒充执行者。任务与消息全文 SHALL 复用 source catalog，不复制进关系摘要。未证实的消息协议、自然语言、时间接近、同名和短 ID SHALL NOT 用于造边或补生命周期。

#### Scenario: 多层委派与有界采集
- **WHEN** Codex 原始记录存在主 Agent → A → B 的唯一显式 child 链，或多个 sibling
- **THEN** 系统 SHALL 保留每一层的父工具与声明调用关系，普通/managed、spool、canonical、SQLite 关闭重开后保持相同事实。
- **AND** child 采集 SHALL 限于明确来源关联，带循环、重复/冲突及资源边界；触及边界明确诊断，不遍历个人库猜 child，不丢失已有委派操作。
- **AND** 相同名称或 ID 前缀的不同实例 SHALL 不合并；无法唯一关联的 child SHALL 不擅自选择父节点。

#### Scenario: 等待结果与子上下文缺失
- **WHEN** 父调用记录明确等待目标及结果报告，或委派后没有可读取 child
- **THEN** 系统 SHALL 独立保留目标、结果来源锚点及所报告状态，不把等待操作/返回/正文当整个任务成功或永久生命周期。
- **AND** 子上下文未采集、单文件未包含、显式父关联缺失、冲突和截断 SHALL 可区分；未知不补运行中/完成/零耗时。
- **AND** 尾部结果不依赖后续消费调用；原 Token、工具/响应计数与计时算法 SHALL 不变。

#### Scenario: 来源与导入安全边界
- **WHEN** Claude 提供明确父工具或 sidechain 身份字段，或来源没有可确认的协作字段
- **THEN** 系统 SHALL 保留明确证据，不按 prompt、type、时间或 sidecar 名称猜父工具；只知 sidechain 不知实例时 SHALL 不冒充 main 或合并所有未知 child。
- **AND** 缺少协议证据的 Qoder 等记录 SHALL 披露“当前记录未提供可确认的协作关联”，不宣称永久不支持。
- **AND** 单文件导入 SHALL 不读取邻居/HOME/个人索引补关系，logical locator 重定位不丢事实、不泄露物理路径，不同 import 的同 ID SHALL 不串联。

#### Scenario: 结构化工具结果与模型消息分别保真
- **WHEN** 当前来源的工具 output 是明确结构化值，而模型消息采用文本块
- **THEN** 工具 Result SHALL 保留可审查的完整结构化内容，不能因没有 text 字段读成空或未记录；normal 与单文件 import SHALL 对同一结果保持一致。
- **AND** 修复 SHALL 限于工具结果提取，不把所有模型消息序列化为 JSON，不双重编码已有字符串；显式空结果、缺失和结构化结果保持可区分，尾结果仍不依赖 consumer。

### Requirement: 明确协议的追加输入协作事实
系统 SHALL 将有明确协议依据的向既有Agent追加输入作为input往来事实，不冒充新的创建委派或完整通信生命周期。当前资格 SHALL 限定Codex function_call的namespace=multi_agent_v1、name=send_input与已审定字段形状；裸名、其他namespace、宿主followup_task与未证实协议不得因名称相似进入该类型。

#### Scenario: 追加声明与提交回执保真
- **WHEN** 当前源含符合明确协议的target与message或合法items，及可选的同call_id结果
- **THEN** 声明 SHALL 保留完整actor/call/tool/target与来源锚点，合法message/items均保留事实；正文仍在source catalog。成功结果仅在明确submission_id和无矛盾错误证据时表示工具报告排队接受，不表示child收到、采用或完成。interrupt仅是请求，工具completed事件不构成消息成功或任务完成证明。
- **AND** 缺结果、明确错误、未知/非法目标、重复call_id、冲突结果及资源上限 SHALL 保守表达，不取最后一条、不按正文/时间补边；结果在当前页之外不等于未记录。旧delegate/wait事实与原Token/计数/时长不变。
- **AND** input SHALL 不增加父创建边/委派数、不复制Agent、不触发邻居或子源发现、不按消息时序分配任务成本；普通/managed、spool、canonical、SQLite关闭重开、单文件导入保真，不同source/import同ID不串联。

### Requirement: 同完整输入累计热点的有界输入身份
服务端 SHALL 仅在明确Codex来源的同一冻结source/import及generation、已确认scope与完整owner、原工具名及当前可信exec_command/executor_reported/codex:exec_command_end家族内，以完整规范化参数记录String相同区分重复调用，不声称原wire类型/字节相同。源层已通过现行JSON序列化形成相同参数记录的不同表示允许同组；新聚合 SHALL 不再canonicalize或恢复来源表示。该身份 SHALL 在脱敏/预览/截断之前计算，仅请求内使用，不以短摘要、脚本名、语义或现场Map字符串化作key；不证明环境、文件内容或业务任务相同，不新建parser/domain/DB、旧索引迁移或持久cache。

#### Scenario: 参数记录字符串、声明归属与顺序无关
- **WHEN** 冻结内容中的inline或response catalog含完整String input/arguments参数记录，且唯一完整call/tool occurrence及源单元归属可核
- **THEN** inline SHALL 绑定其声明call，catalog SHALL 通过所属call的完整source refs/sequence关联，不仅按裸ID putIfAbsent；工具原名、scope/owner、declaredByCallId和toolCallId SHALL 一致。同一源单元的镜像不重复计次，catalog/inline/tool先后不改变资格或结果。
- **AND** 同occurrence多条独立声明、重复call/工具、矛盾镜像、无归属同ID候选、来源归属冲突或catalog候选所需refs不完整 SHALL 使相关父组新提示无资格；唯一所属call的inline输入无需虚构refs，真实inline声明不因refs为空被排除，不任选first/last、不读邻居/HOME补证据；现有定位不能唯一识别的裸ID复用不得新增提示。跨scope/owner/source/import同ID不串联。
- **AND** 上述“独立工具 Input 不依赖已确认模型 owner”仅允许内容可读，不放宽本场景的 call-owned 归属、严格镜像或全父组累计资格；不得以独立 Input 反推 owner 或补 refs。
- **AND** 若规范化声明字段仍为Map/数组/标量、双参数字段歧义、缺失、空串/纯空白、已截断或完整性不足、超长输入 SHALL 不猜字符串。原始结构化参数经既有Codex adapter得到的完整JSON String SHALL 以记录层身份处理，不误称原生来源类型保真。仅手工inline投影不能证明normal目标可行；合成原始Codex正常扫描与import的实际inline/引用形态 SHALL 单独核实，不为测试伪造catalog，无法保真时返root决定，不越界重构源管线。

#### Scenario: 完整身份不随显示摘要合并
- **WHEN** 不同完整参数记录String经脱敏或180字符预览变成相同文本，或记录中的JSON空白/键顺序/转义、参数、包装、Unicode规范形不同
- **THEN** 系统 SHALL 不归并这些输入；不重序列化或通用canonicalize，一个多行script仍一次调用。内部指纹 SHALL 覆盖整个原String及长度，使用逐UTF-16 code unit无损编码或严格拒绝非法代理项的编码，不因替换字符、前缀截断或Unicode规范化意外合并。
- **AND** 读取后仅保留有界内部指纹、计数、安全摘要和完整稳定证据，原文与指纹 SHALL 不输出到API/DOM/log/错误或持久cache。安全摘要 SHALL 来自本occurrence原String并复用现行脱敏，不复用可能误绑的裸ID预览。

#### Scenario: 全范围输入覆盖与资源上限
- **WHEN** 完整冻结范围正在计算同输入候选
- **THEN** 新增计算 SHALL 限定每类call/tool/catalog/内容单元最多16,384项、refs/sequence keys合计65,536、元数据字符串每项1,024及总计4,194,304个UTF-16 code units、参数记录单条65,536及所有检查声明（含镜像）合计4,194,304个UTF-16 code units、递归depth8、每源节点1,024及整请求节点262,144。为本段资格/汇总至多三轮顺序遍历，其中相对既有实现新增cursor最多两个，优先复用既有遍历；不得把既有预览/分页cursor成本声称为本段总成本，不逐tool/call扫描全catalog、不toArtifact、不保留全量原Input。全局超限 SHALL 停止新收集并省略全部新提示，不以已读前缀冒充全范围；已有诊断与计量不因此被清零或取消。
- **AND** 一个父累计组全部已记录同名调用的输入身份 SHALL 100%可确认才输出新提示；任一未知/冲突/超限整组省略，不展示可识别子集“最大”。输入识别覆盖 SHALL 与时长覆盖独立；计时允许部分覆盖，仅受支持原始纳秒进入BigInteger和，未知不补零、其他口径不混入。

#### Scenario: 精确累计与稳定可选最大项
- **WHEN** 同父组至少两种合格完整输入且某个输入的可信已测调用至少重复两次
- **THEN** 系统 SHALL 按精确已测纳秒总和选至多一个输入组，以稳定代表的完整scope/owner/call/tool身份破同值；代表为该输入组可信成员完整身份最小者。只有最大组自身满足重复/可核证据资格才输出，不退而挑第二组伪称最大。零、亚毫秒及超过long的合法累计和 SHALL 不丢精度。
- **AND** 输出 SHALL 仅含安全摘要/完整工具证据、该输入组精确已测和及measured/total/unknown/other、父组不同输入数与完整输入识别覆盖；缺省不表示零或只有一种输入。旧累计100s/200、原最长代表、原覆盖/排除/模型未知/协作tuple SHALL 不变，不以计量缺测覆盖代替输入身份覆盖。

### Requirement: 导入声明的真实来源归属与严格镜像
受支持的Codex单文件导入 SHALL 在真实响应分配时保留具体工具声明的源位置和完整call/tool身份，使用既有sourceUnitRefRanges与catalog表达归属，使同一合法来源在normal/import中具有相同的完整输入热点能力。关联 SHALL 不以裸ID、相同Input、时间相邻或列表位置猜测，不放宽完整身份、全父组覆盖、镜像、资源或隐私保护；短暂关联不新增持久schema、DB或HTTP协议。

#### Scenario: 完整读取后才使用源坐标
- **WHEN** import将解析后的eventIndex关联到原始事件目录
- **THEN** 系统 SHALL 核实同一私有分析文件的严格对象数、Codex实际producer计数、单文件无子来源贡献及完整读取，并在整个分析生命周期保持文件独占、核对读取前后内容指纹；Success、无ERROR或size/mtime相等均不足以证明。计数不足、内容变化或I/O错误 SHALL 不发布前缀假refs，不修补猜测offset。
- **AND** blank/BOM、历史前缀和同event的fallback SHALL 不造成坐标重编号或工具owner继承；record ordinal、eventIndex及工具槽位 SHALL 分别保留。当前Codex不接受的metadata SHALL 仍按现规则拒绝，不为建立坐标新增来源支持。

#### Scenario: 源声明与所属响应保持可核关系
- **WHEN** 源位置、实际分配call和规范化工具身份均唯一可核
- **THEN** 所属call SHALL 精确引用完整catalog key，目录声明 SHALL 复用该次分配生成的完整规范化inline unit，包括text、规范化id、原name和完整input；canonical写读及SQLite关闭重开后关系不变。原raw事件、原ID/参数包装和Result SHALL 仍按既有脱敏入口可查。
- **AND** 全部独立目录声明 SHALL 保留，多块按结构路径/数组下标枚举，不以结构相等去重或将part位置与工具槽位zip。未解析的nested、无owner、独立重复、冲突及历史声明 SHALL 不伪装镜像、删除或first/last覆盖；不能从catalog新造call/tool。未消解冲突仍使相关父组新提示无资格，原计量不受影响。

#### Scenario: 正常来源与导入的相同热点
- **WHEN** 同一完整合成来源含200次可信500ms调用、20alpha/180beta，分别经过normal与真实单文件import
- **THEN** 两者 SHALL 保持父100s/200、原最长alpha500ms，并生成beta90s/180及2种完整输入事实；仅beta一项缺时长时为父99.5s/199/200、beta89.5s/179/180且缺测1，输入识别仍200/200，不补零。
- **AND** 既有样例定位 SHALL 核到实际owner/Input/Result，默认同记录多委派、子Agent再委派、完整协作身份和有效返回焦点保持；不增加默认HTTP、原文预载或把累计归为一次调用/委派成本。真正无归属、冲突、未知输入或超限仍省略新提示，不同scope/source/import/generation不串联。

### Requirement: 工具结果 occurrence 与本地输入的显式包含

工具的一次独立来源结果 SHALL 与合并的工具全文、模型响应及本地输入引用分别建模。包含关系仅表达本地记录，不证明提供方收到、模型采用或任务完成。

#### Scenario: 同文结果与镜像具有不同身份规则
- **WHEN** 归一化记录向调用分配工具结果
- **THEN** inline 与独立结果目录 SHALL 保留同一次真实来源分配的共享内部锚点；不同来源位置即使正文相同仍是不同结果，同源镜像仅在身份及内容一致时去重，不从正文、时间或裸工具ID补边。EOF及显式空结果 SHALL 保留，缺失不补空。
- **AND** 锚点 SHALL 贯通正常扫描发布及独立重开；内部源坐标、物理路径和正文指纹不直接输出至API。无锚点仍可分类展示安全正文，但不能据此给准确反向入口。

#### Scenario: 每条输入引用与全部已确认目标
- **WHEN** 本地输入明确包含某个结果来源单元
- **THEN** 投影 SHALL 保留准确call、request及独立reference，同一输入的多次引用各可定位，一个结果的多个目标全部有界可达；不得用单值consumer摘要或相同文本替代完整关系。不同scope/owner/import或歧义身份 SHALL 不串联。
- **AND** 每个目标的本地记录号及主/子作用域 SHALL 来自真实调用metadata，不从前端已加载列表或provider请求数推导。归因入口 SHALL 用同session/import的完整调用身份，不要求调用者虚构轮次或轮内位置；旧位置路由的严格范围校验保持。

#### Scenario: 不完整metadata不授予前缀全集资格
- **WHEN** 来源集合、header声明总量、调用/工具/目录/引用数量或镜像无法完整核验
- **THEN** 系统 SHALL 保留可读的安全正文并明确unknown/partial/ambiguous；完整无引用与尚不能确认 SHALL 区分，不把读取错误降为空关系。关系身份 SHALL 在同一冻结内容的独立reader间稳定，不用随机实例身份。
- **AND** 投影 SHALL 受既有metadata上限约束：call/tool/catalog各16,384、refs/sequence及遍历位置65,536、字符串单项1,024及合计4,194,304个UTF-16 code units；不扩大预算，不建持久全图或长期原文缓存。

#### Scenario: 显式有界读取与准确后窗
- **WHEN** 用户显式读取结果或输入
- **THEN** typed视图 SHALL 默认20项、硬上限100，并保留手动续页及准确target所在窗口的一次读取；默认详情不增加正文/关系预载。首次Result当前页前20项各最多1个准确目标预览、总计不超过20，复用同一reader metadata，不为每项重建reader/全源扫描。预览未载入不等于零目标。
- **AND** opt-in SHALL 仅用于受支持的准确request或tool-result身份；整轮聚合Request等合法载荷继续现原文路径，不将聚合ID当call、不先失败再兼容回退，不丢无模型调用的原输入。
- **AND** HTTP句柄 SHALL 绑定当前normal/import、冻结内容代、visibility、payload、occurrence及分页条件，服务端重新核验所属与资格；非法400、不存在404、换代409与读取失败500区分，不跨scope兜底。
- **AND** typed正文 SHALL 先经当前SensitiveFieldPolicy；空、missing、mask与真实truncated分开，旧工具级全文/Copy不丢尾部。bulk SHALL 复用现私有offset生命周期，不将全部正文驻留内存。

#### Scenario: 静态档案使用相同安全关系
- **WHEN** 导出已收录的call与工具内容
- **THEN** 静态档案 SHALL 使用同typed来源与安全语义保留输入分类、独立结果、完整原始记录及全部已确认关系，不受在线分页裁掉已收录内容。仅已收录且身份确认的reference生成准确原生HTML片段；未知或不可到达明确说明，不新增在线补取。
- **AND** 原大小拒绝、流式写入和私有索引关闭保护保持；MHTML的原生展开与已知片段导航限制不扩大为在线modal/协作交互承诺。
