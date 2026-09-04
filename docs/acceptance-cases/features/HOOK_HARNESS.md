# Minimal Harness 验收用例

## 范围

| 项 | 内容 |
|---|---|
| 模块 | 显式 Gate、OpenSpec、共享 agent/skill 入口与静态安全策略 |
| 关联源码 | `scripts/gates/`、`scripts/gates/checks/`、`scripts/harness/python_env.py`、`scripts/openspec/`、`harness/` |
| 关联测试 | `tests/gates/`、`tests/harness/`、`tests/quality/` |
| 主要风险 | Gate 伪 PASS、错误 path routing、隐私/密钥检查缺失、工具环境不确定或隐式生命周期动作 |

## 验收用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
| HOOK-HARNESS-007 | P0 | data | Gate 结构化报告 | 测试 Evidence 与 Presentation 公共 contract | PASS 输出简洁，FAIL/BLOCKED 保留首因，schema v5/hash 正确且诊断有界 | pytest | — | `tests/gates/test_receipt_store.py`; `tests/gates/test_terminal_ui.py` |
| HOOK-HARNESS-008 | P0 | data | 高价值质量门禁 | 运行领域质量检查 contract | 隐私、密钥、生成路径、skip/warning 等规则按预期触发 | pytest / JUnit | — | `tests/checks/test_repository_check_outcomes.py`; `tests/gates/test_outcome_classifier.py`; `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/CssOwnershipRuleTest.java`; `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/RawInnerHtmlRuleTest.java`; `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/LayoutInlineStyleRuleTest.java` |
| HOOK-HARNESS-009 | P0 | data | 质量产物结构 | 测试 Gate service 的当次运行产物 | 产物使用 ignored 质量目录，路径稳定且不会进入 candidate | pytest | — | `tests/gates/test_cli.py`; `tests/harness/test_doctor_output.py` |
| HOOK-HARNESS-010 | P0 | data | Gate execution | 测试 command adapter、process supervisor、outcome classifier 与 run orchestrator | Catalog 命令自然完成；heartbeat/STALL 不 kill；仅显式中断清理进程组；warning/skip/not-run/unavailable 不得 PASS | pytest | — | `tests/gates/test_command_adapter.py`; `tests/gates/test_process_supervisor.py`; `tests/gates/test_outcome_classifier.py`; `tests/gates/test_run_orchestrator.py`; `tests/quality/test_python_env_contract.py` |
| HOOK-HARNESS-011 | P0 | data | 稳定内部标识 | 测试 full 与 incremental 文本范围 | 仓库内部 catalog、payload、schema 和 profile 标识使用稳定无版本后缀名称 | pytest | — | `tests/quality/test_current_version.py` |
| HOOK-HARNESS-012 | P0 | data | Gate 失败语义 | 测试 Gate run fail-closed 逻辑 | incremental Gate 的 BLOCKED/FAIL 保留真实状态并写入 immutable receipt | pytest | — | `tests/gates/test_cli.py`; `tests/gates/test_receipt_store.py` |
| HOOK-HARNESS-013 | P1 | data | 静态产品契约 | 测试模板/CSS/JS 等静态契约 | 桌面 viewport 约束明确，JS 内容完整，CSS 规则和 selector ownership 有效 | JUnit | — | `java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/StaticResourceContractRuleTest.java` |
| HOOK-HARNESS-014 | P1 | data | Minimal Harness 结构 | 验证 manifest、agent policy、skill registry 与公开入口 | 共享 agent/skill、OpenSpec 和 Gate 入口完整，生命周期动作由客户端显式管理 | pytest | — | `tests/harness/test_doctor_output.py`; `scripts/harness/validate_harness_structure.py` |
| HOOK-HARNESS-015 | P1 | data | OpenSpec 布局 | 验证 OpenSpec specs/changes/schema/template | 非平凡变更可显式创建和验证，不依赖 pre-write Hook 授权 | manual | — | `scripts/openspec/validate_layout.py`; `scripts/openspec/validate_active_change.py` |
| HOOK-HARNESS-016 | P0 | data | Java 浏览器 fixture 隔离 | 启动 Playwright 受管 Java fixture server 后读取 sessions summary 和 rows API | 只暴露 45 个 synthetic Claude sessions，project key 仅来自受控 fixture，Codex/Qoder 用户目录不会进入索引 | Playwright | `testDataPrivacy`; `credentialLeakScan` | `tests/playwright/fixture-server-isolation.spec.js` |
