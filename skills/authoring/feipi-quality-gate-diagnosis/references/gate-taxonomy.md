## Required baseline

所有 required baseline gate 必须全部 PASS，任何一个失败或 skipped 都不能视为整体通过。

| Gate | 脚本路径 |
|---|---|
| Agent runtime manifest | `scripts/quality/check_agent_runtime_manifest.py` |
| Agent hook parity | `scripts/quality/check_agent_hook_parity.py` |
| 未提交本地路径检查 | `scripts/quality/check_no_committed_local_paths.py` |
| Agent permission policy | `scripts/quality/check_agent_permission_policy.py` |
| Agent policy size | `scripts/quality/check_agent_policy_size.py` |
| Agent rules sync | `scripts/quality/check_agent_rules_sync.py` |
| Skill registry | `scripts/quality/check_skill_registry.py` |
| Agent entry parity | `scripts/quality/check_agent_entry_parity.py` |
| 必要质量门合集 | `scripts/quality/run_required_quality_gates.py` |
| Doctor | `scripts/harness/doctor.sh` |

## Doctor

Doctor 脚本（`scripts/harness/doctor.sh`）是综合体检脚本，覆盖：

- 必要文件存在性检查（AGENTS.md、CLAUDE.md、settings.json 等）。
- Hook 入口脚本存在性（`.claude/hooks/`、`.codex/hooks/`、`.qoder/hooks/`）。
- Harness 文件存在性（manifest.yaml、agent-runtime.md）。
- Python 环境检查（resolver、依赖安装）。
- 配置 JSON 格式校验。
- Shell 脚本语法检查。
- Python 源码编译检查。
- 所有 required quality gate 运行。
- 个人文件和临时目录检查。
- OpenSpec runtime state Git 追踪检查。

Doctor 失败时需要按输出逐项定位，不要试图一次性修复所有问题。

## Stop check

Stop check 在 agent 停止前运行，检查：

- 是否有未提交的受保护路径变更。
- 是否有真实 session 数据被修改。
- 是否有 required gate 未运行。
- 是否有 skip 被新增。

Stop check 失败时 agent 不能停止，必须先诊断和修复。

## Java gates

Java gates 覆盖：

- 编译：`./gradlew compileJava` — 所有模块必须编译通过。
- 测试：`./gradlew test` — 所有测试必须通过。
- PMD：`./gradlew pmdMain` — 静态分析必须无违规。

Java gate 失败时先定位失败模块和具体错误，再做最小修复。不要全量重构。

## UI gates

UI gates 覆盖：

- Session detail 静态检查：`scripts/quality/check_session_detail_static.py`。
- JS action handler 检查：`scripts/quality/check_js_action_handlers.py`。

UI gate 失败时定位失败的模板或 JS 文件，确认变更是否符合 UI 契约。

## Agent runtime gates

Agent runtime gates 覆盖：

- Skill registry 完整性：`check_skill_registry.py` — 源目录、入口链接、必需文件、命名规范。
- Agent runtime manifest 完整性：`check_agent_runtime_manifest.py` — 顶层字段、policy files、hooks、shared skills。
- Agent entry parity：`check_agent_entry_parity.py` — Claude/Codex agent 入口对等性和 skill 引用。
- Hook parity：`check_agent_hook_parity.py` — 三平台 hook 一致性。
- Agent rules sync：`check_agent_rules_sync.py` — 规则文件同步状态。
- Agent policy size：`check_agent_policy_size.py` — 策略文件大小限制。

Agent runtime gate 失败时通常是配置漂移（registry/manifest 与实际状态不一致），修复时保持配置和实际状态一致。
