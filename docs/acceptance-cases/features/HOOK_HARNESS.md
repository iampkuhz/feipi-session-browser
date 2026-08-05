# Minimal Harness 验收用例

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 显式 Gate、OpenSpec、共享 agent/skill 入口与静态安全策略 |
| 关联源码 | `scripts/gates/`、`scripts/checks/`、`scripts/harness/python_env.py`、`scripts/openspec/`、`harness/` |
| 关联测试 | `tests/gates/`、`tests/harness/`、`tests/quality/` |
| 主要风险 | Gate 伪 PASS、错误 path routing、隐私/密钥检查缺失、工具环境不确定或本地 Hook 再次阻断普通修改 |

## 已退役边界

仓库不再维护平台 Hook adapter、Session Registry、checkout writer lease、mutation baseline、Stop controller、自动 commit 或自动 integration。对应历史用例 `HOOK-HARNESS-001`–`006`、`016`–`024` 随生产能力一起退役，不保留兼容测试。

## 验收用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| HOOK-HARNESS-007 | P0 | data | Gate 结构化报告 | 测试 `scripts.gates.report` 公共 contract | PASS 输出简洁，FAIL/BLOCKED 保留首因，JSON schema/hash 正确且诊断有界 | pytest | — | `tests/gates/test_report.py` |
| HOOK-HARNESS-008 | P0 | data | 高价值质量门禁 | 运行领域质量检查 contract | 隐私、密钥、生成路径、skip/warning 等规则按预期触发 | pytest / JUnit | — | `tests/checks/test_repository_check_outcomes.py`; `tests/gates/test_executor.py`; `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/CssOwnershipRuleTest.java`; `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/RawInnerHtmlRuleTest.java`; `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/LayoutInlineStyleRuleTest.java` |
| HOOK-HARNESS-009 | P0 | data | 质量产物结构 | 测试 Gate service 的当次运行产物 | 产物使用 ignored 质量目录，路径稳定且不会进入 candidate | pytest | — | `tests/gates/test_cli.py`; `tests/harness/test_doctor_output.py` |
| HOOK-HARNESS-010 | P0 | data | Gate executor | 测试唯一 executor 的命令、超时、环境与资源隔离 | catalog 命令被执行，warning/skip/timeout 不得 PASS | pytest | — | `tests/gates/test_executor.py`; `tests/quality/test_python_env_contract.py` |
| HOOK-HARNESS-011 | P0 | data | 当前源码政策 | 测试四类当前源码规则 | 源码不保留历史标记、Harness 日志、非桌面视口或无效静态垫片 | pytest | — | `tests/quality/test_current_source_policy.py` |
| HOOK-HARNESS-012 | P0 | data | Gate 失败语义 | 测试 Gate service fail-closed 逻辑 | incremental Gate 的 BLOCKED/FAIL 都必须归约为 NOT_PASS，并写入当次 artifact | pytest | — | `tests/gates/test_cli.py::test_service_exposes_not_pass_and_keeps_detail` |
| HOOK-HARNESS-013 | P1 | data | 静态产品契约 | 测试模板/CSS/JS 等静态契约 | 产品静态资源满足稳定结构与安全规则 | JUnit | — | `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/StaticResourceContractRuleTest.java` |
| HOOK-HARNESS-014 | P1 | data | Minimal Harness 结构 | 验证 manifest、agent policy、skill registry 与公开入口 | 不要求 Hook/Session Runtime 文件存在，保留共享 agent/skill 与 Gate 入口 | pytest | — | `tests/harness/test_doctor_output.py`; `scripts/harness/validate_harness_structure.py` |
| HOOK-HARNESS-015 | P1 | data | OpenSpec 布局 | 验证 OpenSpec specs/changes/schema/template | 非平凡变更可显式创建和验证，不依赖 pre-write Hook 授权 | manual | — | `scripts/openspec/validate_layout.py`; `scripts/openspec/validate_active_change.py` |
