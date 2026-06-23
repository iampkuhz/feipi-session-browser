# SI-040 Design: Normalized Artifact 到 Index Row 映射与不变量

## 1. 目标

把 verified normalized artifact 转为 typed session row，集中唯一映射和缺失语义：
- 逐列建立 normalized field -> DB column 映射矩阵
- 禁止空字符串无条件吞掉 absent/unknown；兼容 DB default 时明确转换
- 时间使用 Instant/Duration，写 DB 时统一格式
- token/count/duration 非负和 conservation 在 domain 边界校验
- 一个 mapper owner，full/incremental 不重复字段列表

## 2. 架构

### 2.1 类型定义

| 类型 | 职责 | 消费者 |
|------|------|--------|
| `SessionRow` record | sessions 表类型化行数据，承载全部列的不可变值 | ArtifactRowMapper 输出，SI-050 write path 消费 |
| `SessionArtifactRow` record | session_artifacts 表类型化行数据 | ArtifactRowMapper 输出，SI-050 write path 消费 |
| `ArtifactRowMapper` | 归一化制品到 index row 的唯一映射器 | SI-050 full scan, SI-060 incremental scan |

### 2.2 映射矩阵

| DB Column | 数据来源 | 缺失处理 |
|-----------|----------|----------|
| session_key | session map `session_key` | 空字符串 -> SessionRow 构造器拒绝 |
| agent | artifact.agent().getValue() | enum 保证非空 |
| session_id | session map `session_id` | 空字符串 -> SessionRow 构造器拒绝 |
| title | session map `title` | 默认空字符串 |
| project_key | session map `project_key` | 默认空字符串 |
| project_name | session map `project_name` | 默认空字符串 |
| cwd | session map `cwd` | 默认空字符串 |
| started_at | session map `started_at` | 默认空字符串 |
| ended_at | session map `ended_at` -> 最后 call timestamp | 空字符串 -> SessionRow 构造器拒绝 |
| duration_seconds | session map `duration_seconds` | 默认 0.0 |
| model_execution_seconds | 预留，当前 0.0 | SI-050 补充 |
| tool_execution_seconds | sum(toolExecutions.durationMs) / 1000 | 默认 0.0 |
| model | session map `model` -> 第一个 call.model() | 默认空字符串 |
| git_branch | session map `git_branch` | 默认空字符串 |
| source | session map `source` | 默认空字符串 |
| user_message_count | count(calls where scope == MAIN) | 默认 0 |
| assistant_message_count | calls.size() | 默认 0 |
| tool_call_count | sum(call.response().toolCallIds().size()) | 默认 0 |
| output_tokens | sum(call.usage().output()) | 默认 0 |
| fresh_input_tokens | sum(call.usage().fresh()) | 默认 0 |
| cache_read_tokens | sum(call.usage().cacheRead()) | 默认 0 |
| cache_write_tokens | sum(call.usage().cacheWrite()) | 默认 0 |
| total_tokens | sum(call.usage().total()) | 默认 0 |
| failed_tool_count | count(toolExecutions where status present) | 默认 0 |
| subagent_instance_count | count(distinct parentCallId from SUBAGENT calls) | 默认 0 |
| indexed_at | System.currentTimeMillis() / 1000.0 | 运行时填充 |
| file_mtime | 调用方传入 | 默认 0.0 |
| file_path | 调用方传入 | 默认空字符串 |

### 2.3 校验放置

| 校验 | 位置 | 理由 |
|------|------|------|
| 主键非空 (sessionKey) | SessionRow compact constructor | DB PRIMARY KEY 约束 |
| CHECK 字段非空 (agent, sessionId, endedAt) | SessionRow compact constructor | DB CHECK 约束 |
| 数值非负 (tokens, counts, durations) | SessionRow compact constructor | DB NOT NULL DEFAULT 0 约束 |
| Token conservation (total = sum of components) | NormalizedCallUsage compact constructor | Domain 层，mapper 信任 |
| callId 唯一性 | NormalizedSessionArtifact compact constructor | Domain 层，mapper 信任 |

### 2.4 信任边界

Mapper 信任归一化制品已通过 domain 不变量验证。只在映射边界执行 DB 约束所需的非空和非负校验，
由 SessionRow 紧凑构造器承担。不在 mapper 内部重复 token conservation 或 callId 唯一性检查。

## 3. 测试覆盖

| 场景 | 测试 | 文件 |
|------|------|------|
| SessionRow 构造器不变量 | SessionRowTest | index-sqlite |
| SessionArtifactRow 构造器不变量 | SessionArtifactRowTest | index-sqlite |
| Session map 字段映射 | ArtifactRowMapperTest | index-sqlite |
| Token 聚合 | ArtifactRowMapperTest | index-sqlite |
| 消息和工具计数 | ArtifactRowMapperTest | index-sqlite |
| 时长聚合 | ArtifactRowMapperTest | index-sqlite |
| Model 回退 | ArtifactRowMapperTest | index-sqlite |
| 子 agent 实例计数 | ArtifactRowMapperTest | index-sqlite |
| SessionArtifactRow 映射 | ArtifactRowMapperTest | index-sqlite |

## 4. Acceptance criteria

- 全部 sessions columns 有映射/默认理由
- Row round-trip 稳定
- 没有 Map-based 通用 mapper
- 错误定位到 field/session
