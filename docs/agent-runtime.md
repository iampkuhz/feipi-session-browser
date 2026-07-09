# Agent Runtime 说明

本文档描述仓库 agent 运行时环境的规约、入口和检查方式。

## 目标

- 统一管理 Claude、Codex、Qoder 三平台的 agent 运行环境。
- 共享规则沉淀到 `skills/`、`harness/`、`scripts/`；平台配置只保留入口。
- 所有受保护路径的变更可追溯、可验证、可复现。

## 唯一真源

| 文件 | 用途 |
|---|---|
| `harness/agent-runtime.manifest.yaml` | agent 环境唯一真源：平台、hook、skill、gate 声明 |
| `harness/skill-registry.yaml` | skill 注册表：source、status、required_files、exposed_in |
| `harness/agent-policy.manifest.yaml` | 策略清单：体积限制、必要短语、受保护根、上下文治理 |

修改 agent 环境时，先更新上述文件，再同步平台入口。

## 平台入口

每个 agent 在 Claude 和 Codex 各有一个入口文件：

| Agent | Claude 入口 | Codex 入口 | 关联 skill |
|---|---|---|---|
| java-backend-implementer | `.claude/agents/java-backend-implementer.md` | `.codex/agents/java-backend-implementer.toml` | `feipi-java-feature-dev` |
| session-ingestion-specialist | `.claude/agents/session-ingestion-specialist.md` | `.codex/agents/session-ingestion-specialist.toml` | `feipi-session-ingestion-dev` |
| ui-implementation-specialist | `.claude/agents/ui-implementation-specialist.md` | `.codex/agents/ui-implementation-specialist.toml` | `feipi-session-detail-ui-dev` |
| mhtml-export-specialist | `.claude/agents/mhtml-export-specialist.md` | `.codex/agents/mhtml-export-specialist.toml` | `feipi-mhtml-export-dev` |
| quality-gate-diagnoser | `.claude/agents/quality-gate-diagnoser.md` | `.codex/agents/quality-gate-diagnoser.toml` | `feipi-quality-gate-diagnosis` |
| privacy-reviewer | `.claude/agents/privacy-reviewer.md` | `.codex/agents/privacy-reviewer.toml` | `feipi-privacy-redaction-dev` |

每个入口必须引用对应的共享 skill 路径。

## Hook parity

三平台 hook 覆盖对比：

| Hook 类型 | Claude | Codex | Qoder |
|---|---|---|---|
| pre_bash | `.claude/hooks/pre-bash.sh` | `.codex/hooks/pre_tool_guard.sh` | `.qoder/hooks/pre_tool_guard.sh` |
| pre_write | `.claude/hooks/pre-write.sh` | `.codex/hooks/pre_write_guard.sh` | `.qoder/hooks/pre_write_guard.sh` |
| post_bash | `.claude/hooks/post-bash.sh` | `.codex/hooks/post_bash_guard.sh` | `.qoder/hooks/post_bash_guard.sh` |
| post_write | `.claude/hooks/post-write.sh` | `.codex/hooks/post_tool_guard.sh` | `.qoder/hooks/post_tool_guard.sh` |
| stop | `.claude/hooks/stop.sh` | `.codex/hooks/stop_check.sh` | `.qoder/hooks/stop_check.sh` |

Claude 额外包含：`session_start`、`subagent_start`、`tool_failure`、`subagent_stop`、`config_change`。

检查命令：`python scripts/quality/check_agent_hook_parity.py`

## Shared skills

所有 skill 真源在 `skills/authoring/`，通过 `harness/skill-registry.yaml` 注册：

| Skill | 路径 | 用途 |
|---|---|---|
| feipi-openspec-orchestrate-change | `skills/authoring/feipi-openspec-orchestrate-change/` | OpenSpec 变更编排 |
| feipi-java-feature-dev | `skills/authoring/feipi-java-feature-dev/` | Java 后端功能开发 |
| feipi-session-ingestion-dev | `skills/authoring/feipi-session-ingestion-dev/` | 会话数据接入 |
| feipi-session-detail-ui-dev | `skills/authoring/feipi-session-detail-ui-dev/` | 会话详情 UI 开发 |
| feipi-mhtml-export-dev | `skills/authoring/feipi-mhtml-export-dev/` | MHTML 导出 |
| feipi-quality-gate-diagnosis | `skills/authoring/feipi-quality-gate-diagnosis/` | 质量门诊断 |
| feipi-privacy-redaction-dev | `skills/authoring/feipi-privacy-redaction-dev/` | 隐私脱敏 |

每个 skill 在 `.agents/skills/`、`.claude/skills/`、`.codex/skills/` 有入口。

检查命令：`python scripts/quality/check_skill_registry.py`

## Required gates

所有 required gate 列表声明在 `harness/agent-runtime.manifest.yaml` 的 `required_gates` 字段：

| Gate | 用途 |
|---|---|
| `check_agent_runtime_manifest.py` | 验证 manifest 结构和文件存在性 |
| `check_agent_hook_parity.py` | 验证三平台 hook 覆盖一致性 |
| `check_no_committed_local_paths.py` | 阻止提交态包含本地绝对路径 |
| `check_agent_permission_policy.py` | 验证权限策略合规 |
| `check_agent_policy_size.py` | 验证 AGENTS.md、CLAUDE.md 体积限制 |
| `check_agent_rules_sync.py` | 验证跨平台规则同步 |
| `check_skill_registry.py` | 验证 skill registry 与实际文件一致 |
| `check_agent_entry_parity.py` | 验证 Claude/Codex agent 入口成对存在 |
| `check_no_real_session_fixtures.py` | 阻止真实 session 数据进入 fixture |
| `check_secret_like_content.py` | 阻止类密钥内容提交 |
| `check_agent_runtime_report.py` | 验证 runtime report 完整性 |
| `run_required_quality_gates.py` | 批量运行所有 required gate |
| `scripts/harness/doctor.sh` | 综合环境检查 |

**规则：required gate 失败、未运行、跳过不得描述为 PASS。不得新增 skip。**

批量运行：`python scripts/quality/run_required_quality_gates.py`

## 本地配置和隐私

- `.claude/settings.local.json` 不提交，已加入 `.gitignore`。
- 提交态不得包含本地绝对路径（gate 检查）。
- 不得复制真实 `~/.claude`、`~/.codex`、`~/.qoder` session 文件进仓库。
- 测试 fixture 必须使用 synthetic 数据。
- 密钥、token、`.env`、`.mcp.json` 等不得出现在仓库中。

相关 gate：
- `check_no_committed_local_paths.py`
- `check_no_real_session_fixtures.py`
- `check_secret_like_content.py`

## 执行非平凡变更的流程

1. 确认变更属于非平凡范围（产品行为、agent/harness/hooks/质量门、目录职责、跨模块改造）。
2. 创建或复用 OpenSpec change：`openspec/changes/<change-id>/`。
3. 编写 `proposal.md`、`design.md`、`tasks.md`、`specs/<domain>/spec.md`。
4. 按 tasks 逐步执行，每步完成后运行相关 gate。
5. 涉及 agent 受保护路径时生成 `harness/reports/<change-id>.json`。
6. Stop/handoff 前运行 `python scripts/quality/run_required_quality_gates.py`。
7. 所有 required gate 通过后才可标记完成。

详细流程参考 `skills/authoring/feipi-openspec-orchestrate-change/SKILL.md`。
