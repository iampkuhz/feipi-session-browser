# 规格增量：harden-openspec-hook-recovery / spec

## 需求

### 需求：创建新变更时必须激活目标 change

`create_active_change.py` MUST 在被调用时将 `.agent/active_change.json` 更新为本次请求的 `change_id`。如果目标 change 文件已经存在，脚本 MUST 保持这些文件不被覆盖。

#### 场景：已有旧 active change 时创建新 change

- **已知** `.agent/active_change.json` 指向旧 change
- **当** 调用 `create_active_change.py --change-id <new-change>`
- **则** `.agent/active_change.json` 指向 `<new-change>`
- **且** 已存在的 change 文件不被覆写

### 需求：受保护编辑前必须验证 active change 基础完整性

`guard_active_openspec_change.py` MUST 在放行受保护文件编辑前验证 active change 目录存在，并且包含 `proposal.md`、`design.md`、`tasks.md`。创建 change 所需的 `openspec/changes/` 和 `.agent/active_change.json` 写入例外 MUST 保留。

#### 场景：active change 目录为空

- **已知** `.agent/active_change.json` 指向一个空的 change 目录
- **当** agent 尝试编辑 `src/`、`scripts/`、`harness/` 或 `.claude/` 下的文件
- **则** PreToolUse hook 阻止编辑
- **且** 输出缺失文件和修复建议

### 需求：Stop 阶段必须产生可恢复阻塞

Stop 验证发现受保护变更缺少 OpenSpec 文件或 evidence 时，MUST 返回阻塞退出码，并 MUST 输出 LLM 可执行的继续步骤。

#### 场景：Stop 时变更不完整

- **已知** 受保护文件存在未提交变更
- **且** active change 缺少必需文件或 evidence
- **当** Stop hook 运行
- **则** hook 返回阻塞退出码
- **且** 输出“继续而不是停止”的修复步骤

### 需求：warning 与 blocking 必须区分

`stop_check.sh` MUST 区分普通 warning 和 blocking gate。普通本地文件提醒可以返回 warning；OpenSpec 验证或质量门失败 MUST 返回 blocking。

#### 场景：OpenSpec 验证失败

- **已知** `stop_validate_change.py` 返回非零
- **当** `stop_check.sh` 汇总结果
- **则** `stop_check.sh` 返回 `EXIT_BLOCK`
