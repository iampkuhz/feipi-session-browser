# Feipi Session Browser — Agent 工程规则

本文件只在任务涉及非平凡开发、OpenSpec、harness、质量门、hooks 或仓库规则改造时读取。普通代码定位、单文件修改、简单文档修改不需要读取本文件。

## 非平凡变更

以下任务属于非平凡变更：

- 新增或改变产品行为；
- 改动 OpenSpec、harness、质量门、hooks、agent 配置；
- 调整目录职责、开发流程、验证流程；
- 跨多个模块的结构性改造；
- 会影响长期维护方式的文档或脚本变更。

非平凡变更应先确认是否已有对应 `openspec/changes/<change-id>/`。如果没有，应先建立或补齐变更任务，再实现代码。

## OpenSpec 规则

- `openspec/specs/` 表示当前长期行为。
- `openspec/changes/<change-id>/` 表示待实施或正在实施的变更。
- 实现应按 `openspec/changes/<change-id>/tasks.md` 串行推进。
- 完成后应同步长期行为到 `openspec/specs/`，再归档变更。
- 不要绕过 OpenSpec 直接大改受保护路径。

## 受保护路径

修改以下路径时必须明确任务目标，并保持变更最小：

| 路径 | 约束 |
|---|---|
| `.claude/` | 影响 Claude Code 运行、权限、hooks、agents |
| `openspec/` | 影响规格真相和变更流程 |
| `harness/` | 影响 agent 工作流和上下文包 |
| `scripts/` | 影响本地验证、运行、质量门 |
| `src/session_browser/` | 产品源码 |
| `tests/` | 测试与回归约束 |
| `CLAUDE.md` / `AGENTS.md` | agent 常驻或按需规则 |

## 文件操作规则

- 先搜索定位，再读取文件。
- 只读取当前任务必需的文件和片段。
- 修改已有文件时优先局部编辑，避免整文件覆写。
- 不覆盖用户未提交改动。
- 不提交缓存、运行数据、真实 session 数据、密钥、token 或个人配置。
- 修改后检查 diff，确认没有引入无关文件。

## 验证原则

只运行与本次改动直接相关的最小验证。

常用验证命令：

```bash
bash scripts/harness/doctor.sh
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/validate_openspec_layout.py
./scripts/session-browser.sh test
python3 scripts/quality/run_quality_gate.py --target session-detail
```

选择规则：

- 改 `harness/`、`openspec/`、`.claude/`、`scripts/`：优先运行 `bash scripts/harness/doctor.sh`。
- 改产品代码或测试：运行 `./scripts/session-browser.sh test`。
- 改 UI 模板、CSS、前端 JS：运行对应 UI 质量门。
- 验证失败时必须保留失败信息，不得把失败或未运行描述为通过。

## 语言策略

- 默认使用简体中文。
- 规约、规格、提示词、模板、流程文档默认中文。
- 代码标识符、命令、路径、API、外部工具名保持英文。
- 面向用户的 UI 文案默认中文。

## 完成标准

- 改动与用户目标直接对应。
- 没有扩大无关范围。
- 已运行最小必要验证，或说明无法运行的原因。
- 文档、脚本、OpenSpec、harness 与代码没有明显冲突。
- 没有纳入个人配置、缓存、运行数据、真实 session 数据或密钥。
