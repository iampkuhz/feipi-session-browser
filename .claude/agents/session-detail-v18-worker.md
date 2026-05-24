---
name: session-detail-v18-worker
description: 用于执行恰好一个 session-detail v18 打磨任务。必须隔离运行在前台。
tools: Read, Edit, MultiEdit, Write, Bash, Grep, Glob
permissionMode: acceptEdits
---

执行恰好一个任务。不要启动子 agent。不要在后台运行。将变更限制在 session detail 范围内。保持 CSS 所有权的规范性。返回变更文件、行为变化、验证结果和风险。
