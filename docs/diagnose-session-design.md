# diagnose session 设计说明

## 使用场景

`diagnose session` 在一次调用中展示 source、raw、normalization、projection 和 divergence，
用于定位 session 数据管道的首个差异。

## 命令

```bash
app-cli diagnose session \
  --agent claude_code \
  --session-id <uuid>

app-cli diagnose session \
  --agent claude_code \
  --session-id <uuid> \
  --format json

app-cli diagnose session \
  --agent claude_code \
  --session-id <uuid> \
  --source-dir ~/.claude \
  --format json --verbose
```

## 输出层级

| 段 | 职责 | 复用路径 |
|---|---|---|
| `source` | 定位会话文件 + subagent 目录 | `ClaudeDiscovery.discoverSessionsWithHistory()` |
| `raw` | JSONL 结构统计 | `ClaudeSourceAdapter.parse()` → `SourceRecord` 列表 |
| `normalization` | 归一化结果摘要 | `NormalizationEngine.normalize()` |
| `projection` | 无 index 的轻量结构投影 | 从 `NormalizedSessionArtifact` 直接提取 |
| `divergence` | 相邻层确定性比较 | 纯规则引擎 |

## 状态语义

| 状态 | 含义 |
|---|---|
| `OBSERVED` | 已观察到数据 |
| `MATCH` | 相邻层一致 |
| `MISMATCH` | 相邻层不一致 |
| `UNAVAILABLE` | 数据不可用（未索引、未归一化等） |
| `ERROR` | 处理出错 |

## Exit Code

| 值 | 含义 |
|---|---|
| 0 | 成功，无 mismatch |
| 1 | 发现至少一个 mismatch |
| 2 | 输入/数据错误（session 不存在、agent 无效等） |
| 3 | 内部错误 |

## schemaVersion

当前为 `diagnose-session.v1`。字段只增不删，顺序稳定。

## 性能预算

warm run < 2s（合成 fixture）；主要耗时在 JSONL 解析。各阶段 timing 已内置于输出。

## 非目标

- 不启动 Web server、不依赖 index/SQLite。
- 不修改 session 文件、index、Git 状态。
- 不复制 `SessionDetailParityAnalyzer` 业务逻辑。
- 输入通过 `--agent`、`--session-id` 和可选 `--source-dir` 定位。
- 不实现 Python diagnose 业务逻辑。
