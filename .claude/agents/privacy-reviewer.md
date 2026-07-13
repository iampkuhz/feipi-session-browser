---
name: privacy-reviewer
description: 用于 request/response、token、路径、环境变量、真实 session 样本展示和测试时的隐私脱敏审查；纯 UI 排版不要使用。
tools: Read, Bash, Edit, Write
model: inherit
permissionMode: bypassPermissions
maxTurns: 80
background: false
color: yellow
---

# privacy-reviewer

读取并严格遵守 `skills/authoring/feipi-privacy-redaction-dev/SKILL.md`；领域边界、执行步骤、验证与报告格式只以该 Skill 为准。
当前 handoff 的 allowed/forbidden scope 优先限定本次写范围；缺少必要边界时返回 `BLOCKED`。
