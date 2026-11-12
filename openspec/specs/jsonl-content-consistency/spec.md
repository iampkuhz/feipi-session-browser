# JSONL 识别与内容一致性

## Requirements

### Requirement: 来源识别只有一个职责所有者
SourceAdapter SHALL 定义本来源合法消息、辅助元数据及未知记录的识别。扫描解析与独立导入 SHALL 复用该来源判断；导入 MUST 保留严格 JSON、UTF-8、资源额度、单会话、安全隔离与错选来源检查，不全量放行未知记录。

#### Scenario: Qoder 包装与元数据
- **WHEN** 合成 Qoder JSONL 包含 role、message 包装、tool_result 和合法辅助元数据
- **THEN** 扫描和导入 SHALL 保留一致消息、调用、工具及计量事实；元数据不得变成消息或调用，未知类型仍拒绝。

### Requirement: 内容表示不改变事实
同等内容的 inline/catalog/sequence SHALL 使用一致的可见文本、引用方向及稳定身份。摘要 SHALL 为完整内容的安全短预览；展开及 payload SHALL 保留实际正文，不串轮、主子调用或同名工具，历史消费不重计执行。

#### Scenario: 用户输入但没有模型调用
- **WHEN** 合成会话只有显式用户输入，没有模型调用
- **THEN** 归一化 SHALL 保留实际输入正文，摘要与观测轮输入正文 SHALL 可读；调用和工具保持零，未知计量不成为已测量零。

### Requirement: 代表性事实覆盖与展示断言分离
核心 JSONL 测试 SHALL 复用已有 synthetic 输入，独立验证预期事实，不只比较两个入口相等。功能测试 SHALL 依据稳定身份、数量、归属及状态；专用文案、视觉和安全交互测试仍保留。

#### Scenario: Codex 双通道与同名工具逆序结果
- **WHEN** 同一输入包含 event/response 双通道或同名不同 call_id 的工具、对象/JSON 字符串 arguments 及逆序结果
- **THEN** 扫描磁盘重读与独立导入 SHALL 保留唯一用户输入与按 toolCallId 配对的 input/result，不按 provider item ID、同名或位置猜配。

#### Scenario: 分页展示文案独立变化
- **WHEN** 仅替换分页展示文案并实际加载后续页
- **THEN** 行为测试 SHALL 继续验证 loaded/total/hasMore 与精确工具主子归属；错误数量、身份或归属仍使测试失败。

### Requirement: 独立工具的声明事实一致
已确定 owner 的 standalone tool_use SHALL 同时出现在该调用的 response.toolCallIds 与会话 declaredTools 中。List 和 managed sequence SHALL 复用已有归属结果，不重新推断模型调用边界。

#### Scenario: 关闭计量帧包含独立工具
- **WHEN** function_call 与 function_call_output 已关联到存在的关闭计量帧
- **THEN** 工具执行 owner、该调用响应工具 ID 与声明计数 SHALL 一致，不能执行两条但声明零条。

### Requirement: 已知计量来源状态不丢弃
逐调用计量来源状态 SHALL 与同一展示范围的用量一起返回；没有来源证据时 SHALL 保持 unknown，不从总量推定已测量。

#### Scenario: 小制品轮次来源状态
- **WHEN** 小制品调用带有 provider_reported 来源状态
- **THEN** 扫描及导入 rounds SHALL 转发同范围既有状态，不因 DTO 默认值降为 unknown。
