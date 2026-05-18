# 质量门禁

本文件描述 feipi-session-browser 仓库的所有质量门禁。

## 门禁层级

### 层级 1：Harness 结构

```bash
python3 scripts/harness/validate_harness_structure.py
```

验证 harness 目录结构和所需文件是否存在。

### 层级 2：OpenSpec 布局

```bash
python3 scripts/harness/validate_openspec_layout.py
```

验证 OpenSpec 目录结构和 schema 合规性。

### 层级 3：标记清理

```bash
python3 scripts/harness/check_no_unfinished_markers.py
```

确保所有待办事项、临时方案、需修复标记都有追踪，不残留。

### 层级 4：任务文件验证

```bash
python3 scripts/harness/validate_task_files.py
```

验证任务文件格式正确且可执行。

### 层级 5：仓库结构

```bash
python3 scripts/quality/validate_repo_structure.py
```

确定性检查 command/skill/hook/spec 结构是否正确安装：
- `.claude/commands/change.md` 存在。
- `.claude/skills/change/SKILL.md` 存在。
- 所有 hook 脚本存在并在 `.claude/settings.json` 中接线。
- 默认 agent 存在且引用 active_change。
- Harness 验证脚本存在。

### 层级 6：Hook 自测

```bash
python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test
python3 scripts/agent_hooks/stop_validate_change.py --self-test
python3 scripts/agent_hooks/inject_session_context.py --self-test
python3 scripts/agent_hooks/log_change_evidence.py --self-test
```

证明 hook 能正确处理正例和反例。

### 层级 7：Doctor

```bash
bash scripts/harness/doctor.sh
```

单一入口健康检查，运行以上所有门禁。

## 何时运行

| 事件 | 门禁 |
|-------|------|
| 任何 harness 变更后 | 层级 1-5 |
| 会话停止前 | 层级 3（通过 Stop hook） |
| 提交前 | 层级 1-5 |
| 仓库迁移后 | 层级 1-7 |
| 上手/首次运行 | 层级 7（doctor） |
