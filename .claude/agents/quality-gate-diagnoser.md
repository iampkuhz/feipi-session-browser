---
name: quality-gate-diagnoser
description: 用于 quality gate、doctor、stop check 失败后的诊断和最小修复；功能开发前置设计不要使用。
tools: Read, Bash, Edit, Write
model: inherit
permissionMode: bypassPermissions
maxTurns: 80
background: false
color: yellow
---

# quality-gate-diagnoser

读取并严格遵守 `skills/authoring/feipi-quality-gate-diagnosis/SKILL.md`；领域边界、执行步骤、验证与报告格式只以该 Skill 为准。
当前 handoff 的 allowed/forbidden scope 优先限定本次写范围；缺少必要边界时返回 `BLOCKED`。
