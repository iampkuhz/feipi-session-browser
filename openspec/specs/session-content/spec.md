# Session 内容中的工具结果与执行观测

## Requirements

### Requirement: 工具结果保留独立于后续消费
当前来源到全新索引的普通与 managed 路径 SHALL 保留每条可唯一关联的实际工具结果，包括没有后续响应的尾部结果和显式空结果。结果正文与存在性 SHALL 复用当前 source-unit/catalog 内容能力，不以消费边为存在条件，不倒灌过去请求，不伪造消费调用，不增加模型响应、工具声明或 Token 计数。

#### Scenario: 尾部结果持久化与空结果
- **WHEN** 工具声明后存在明确结果，但没有后续模型记录
- **THEN** canonical 与 SQLite 关闭重开后的工具 Result SHALL 保持可读，消费关联 SHALL 为空，结果存在摘要 SHALL 为真；缺少结果的工具仍为 missing。
- **AND** 显式空结果 SHALL 为 available 且正文为空；摘要只收集稳定身份的存在信息，不为每个工具读取全文。来源、scope 和 occurrence SHALL 防止同名或同裸 ID 串绑。

#### Scenario: 有内容的当前静态档案
- **WHEN** 新建普通 compact 或 managed 会话有可用内容，使用既有 HTML/MHTML 导出路由
- **THEN** 现有静态 snapshot SHALL 包含全部已发布 call/tool 正文，不受在线分页/筛选裁剪，不因 artifact 同时存在而退为元数据；使用原生 details 和片段来源链，不新增 live tabs/modal/filter。
- **AND** manifest 大小 SHALL 对应实际档案；standard 脱敏、50 MiB 超限拒绝和现有 data-bundle 合同不因路由修复改变，不增加旧索引兼容或迁移。
- **AND** HTML SHALL 支持原生工具到声明记录的片段定位。MHTML SHALL 保留相同完整正文和原生展开；档案内 SHALL 明确部分浏览器不执行 MHTML 页内跳转，需定位时优先使用 HTML 或手动展开声明记录。此浏览器限制不应被标成已修复，也不通过脚本或新框架伪装同等导航支持。

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
