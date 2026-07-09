## 失败输出采集

诊断的第一步是完整采集失败输出：

1. **复制完整命令**：包括所有参数和环境变量。
2. **记录 exit code**：`echo $?` 获取，不是 0 的值都需要诊断。
3. **保留完整 stdout 和 stderr**：不要截断，不要概括。gate 脚本通常输出 `[gateName] FAIL: <message>` 格式，提取 message 部分。
4. **注意多 gate 失败**：doctor.sh 等综合脚本可能有多个 gate 失败，逐一记录。

采集后不要立即修复，先完成触发 target 定位。

## 触发 target 定位

从失败输出中提取具体的触发 target：

- **Skill registry 失败**：target 是 skill 名称和缺失的属性（如 "skill feipi-xxx source 不存在"）。
- **Manifest 失败**：target 是缺失的顶层字段或无效引用（如 "required skill 目录不存在: feipi-xxx"）。
- **Agent parity 失败**：target 是 agent 名称和缺失的入口文件。
- **Hook parity 失败**：target 是缺失或不一致的 hook 文件。
- **编译/测试失败**：target 是失败的模块、类或方法。
- **Doctor 失败**：target 是具体检查项（文件存在性、JSON 格式等）。

定位后读取对应的 gate 脚本源码，理解检查逻辑。

## 环境失败

环境失败的特征：

- Python 不可用或版本不匹配。
- 必要依赖未安装。
- 脚本文件本身不存在。
- 权限不足。

处理方式：报告 `BLOCKED`，说明缺少什么。**不要**尝试安装依赖、修改 Python 版本或更改权限。这些操作超出本 skill 范围。

输出格式：
```
Status: BLOCKED
原因: <具体缺失项>
需要的环境修复: <建议操作>
```

## Fixture 失败

Fixture 失败的特征：

- 测试文件引用不存在的 fixture 文件。
- Mock 数据缺失导致测试跳过或失败。
- 示例配置文件不存在。

处理方式：补最小必要的 fixture 文件。Fixture 应：

- 放在测试约定的 fixture 目录下。
- 内容最小化，只包含 gate 或测试需要的字段。
- 不包含真实 session 数据、密钥、token。
- 不超出当前 gate 失败的范围。

## 代码失败

代码失败的特征：

- 产品代码不满足 gate 断言（如缺少 SKILL.md、registry 条目与实际不匹配）。
- 编译错误（缺少 import、类型不匹配、方法签名变化）。
- 测试断言失败。

处理方式：做最小修复。修复原则：

- 只改与当前 gate 失败直接相关的代码。
- 不重构、不优化、不扩大修改范围。
- 不改与当前 gate 无关的配置文件。
- 修复后 gate 必须 PASS，且不能引入新的 gate 失败。

## Gate 缺陷

Gate 缺陷的特征：

- Gate 脚本逻辑错误导致误报（如检查了不应该检查的条件）。
- Gate 脚本与最新的项目结构不兼容。
- Gate 脚本的解析逻辑有 bug。

处理方式：修复 gate 脚本并补充自测。修复原则：

- 不要删除有效质量门来满足 gate。
- 修复后的 gate 应同时能检测真正的失败（不漏报）和不误报正常状态。
- 如果可能，为修复的 gate 逻辑添加单元测试。

## BLOCKED 输出

当无法在当前环境或权限下修复时，输出 BLOCKED：

```
Status: BLOCKED
失败 gate: <gate 名称>
Exit code: <exit code>
失败类别: <环境缺失/fixture 缺失/代码失败/配置漂移/gate bug>
失败 target: <具体 target>
失败详情: <完整错误信息>
BLOCKED 原因: <为什么无法修复>
建议操作: <需要人工介入的操作>
```

BLOCKED 不是失败，是诚实的状态报告。以下情况必须 BLOCKED：

- 环境缺失且不在本 skill 修复范围内。
- 需要跨 allowed scope 修改文件。
- 需要人工判断的设计决策。
- 多个 gate 互相矛盾，需要人工协调。
