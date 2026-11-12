---
name: feipi-quality-gate-diagnosis
disable-model-invocation: true
description: 用于 Gate、doctor 或显式质量检查未通过后的分层诊断、快速反馈与最小修复；功能开发前置设计不要使用。
---

# 质量门诊断与修复

先读取并遵守[分层修复反馈闭环](references/repair-loop.md)。修复遵循“复现 → 单点反馈 → 相关回归 → 最终 Gate”；失败按有证据的根因归组，不以累计修复次数或完整 Gate 的一次失败决定停止。

## 最小上下文与边界

读取失败命令、exit code、当前 receipt 的失败步骤及对应完整日志，再读直接相关代码。Gate 定位与原生命令选择以 docs/gates/gate-control-plane.md、docs/development/README.md 和 scripts/gates/cli.py list/plan 为准，不复制静态矩阵。

普通功能开发使用领域 skill；OpenSpec/harness/Gate 契约改造先走 feipi-openspec-orchestrate-change。子 agent 只在 handoff allowed scope 内修复，越界时将精确缺口交回 main；main 仍需评估可安全继续的工作，不能把子任务 BLOCKED 当整体停止理由。

## 执行

1. 保存当前症状、预期行为和原失败证据，明确最小复现/验证命令；无覆盖才补合成用例。
2. 分类为产品/断言、fixture/环境、配置、Gate 自身或输入变化；环境缺口先安全核查，不越权安装或改个人配置。
3. 每项修复立即重跑原单点。失败回到诊断，通过再跑实际消费者的相关回归。不每修一项就跑整套 Gate 或 doctor。
4. 有效进展继续；无进展先调整诊断。停止条件、证据复用、依赖放行和阻塞报告遵守共享闭环，不用平台 max_attempts 限制修复。
5. 相关问题解决且输入稳定后，显式运行整个工作区 python3 scripts/gates/cli.py run --mode incremental。失败再回局部闭环，直至通过或确有外部阻塞。doctor/selector 仅在验证相应改动时选择，不每轮重复。
6. 检查 diff 和反向效果，不降低阈值/断言、不新增 skip/skipif/fixme、不覆盖他人改动。最终 required 未通过不得称 PASS。

## 输出

复用已有 tasks/评论或[报告模板](templates/report.md)，记录问题分组、修前证据、最小修改、单点与相关结果、最终凭证、实际效果及剩余条件。日志不可仅为旧 receipt；缓存命中不称测试重跑。运行产物放 tmp/，不纳入真实 session 或凭据。
