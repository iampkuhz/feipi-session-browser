# Subagent Catalog

本目录定义项目中所有可复用 subagent 的角色声明。

## 文件说明

| 文件 | 用途 |
|---|---|
| `catalog.yaml` | subagent 角色注册表，声明每个 subagent 的读写范围、触发规则与校验命令 |

## 字段规范

每个 subagent 必须包含以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 唯一标识，不可重复 |
| `kind` | enum | `readonly-analysis` / `restricted-writer` / `verification-only` |
| `read_scope` | list[string] | 允许读取的路径模式 |
| `write_scope` | list[string] | 允许写入的路径模式 |
| `forbidden_scope` | list[string] | 禁止读写的路径模式 |
| `trigger_rules` | list[string] | 触发条件：路径模式或语义标签 |
| `validation_cmds` | list[string] | 任务完成后运行的校验命令 |
| `retry_policy` | string | 重试策略，例如 `rate-limit-only` |

## 并发约束

`execution.llm_concurrency: 1` — 同一时刻只允许一个 LLM subagent 执行。
主 agent 不得 busy-wait，子 agent 上下文隔离。

## 校验

```bash
python3 scripts/harness/validate_subagent_catalog.py
```
