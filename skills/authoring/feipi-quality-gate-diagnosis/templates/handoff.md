# 诊断子任务

按[共享 subagent contract](../../feipi-openspec-orchestrate-change/references/subagent-contract.md)和 policy 填写 handoff 所有字段、互斥文件范围及身份，不在此复制协议。

## 必要问题证据

- 原失败、期望行为、当前 receipt/日志与根因假设。
- 本任务允许的最小修复范围及禁止范围；不读真实 session/凭据，不覆盖他人差异。
- 单点复现命令与修前结果；无现有覆盖时补最小合成用例。
- 单点通过后的实际消费者回归命令；失败返回局部诊断。
- 由 main 负责最终整个工作区增量 Gate；子任务不每步重跑 doctor、其他 Gate 或整套。

先读[修复闭环](../references/repair-loop.md)，按需读[取证](../references/failure-diagnosis.md)或[分类](../references/gate-taxonomy.md)。单点和相关验证必须如实报告；越界或无安全替代时交回精确障碍，不擅自结束整个工作。
