# 验收用例总账

本目录是跨 Pytest、JUnit 和 Playwright 维护验收用例 ID、人类验收说明与自动化测试
绑定的唯一位置。它是“用例管理总账”，**不是 Gate Target，也不负责执行测试**。

```text
docs/acceptance-cases/
├── README.md
├── TEST_CASE_ID_RULES.md
└── features/
    ├── DATA_SOURCES.md
    ├── DATA_INDEX.md
    ├── DATA_PRESENTERS.md
    ├── ROUTES_AND_API.md
    ├── UI_DASHBOARD.md
    ├── UI_SESSIONS_LIST.md
    ├── UI_SESSION_DETAIL.md
    ├── UI_PROJECTS.md
    ├── UI_GLOSSARY.md
    ├── UI_GLOBAL_VISUAL.md
    ├── UI_INTERACTIONS.md
    └── HOOK_HARNESS.md
```

## 维护规则

- 每个验收用例 ID 必须在 `features/*.md` 的“验收用例”表中定义。
- 每个 `features/*.md` 至少包含两个 markdown 表格：上方“范围”表和下方“验收用例”表。
- “验收用例”表格行必须包含用例 ID、优先级、分层、场景、怎么测、必须断言、测试类型、关联检查和代码位置。
- 测试里的 `@pytest.mark.contract_case(...)` marker 应能在本目录找到对应用例定义。
- 自动化用例的代码位置指向真实测试文件，表格行和测试绑定使用同一 ID。
- 页面行为细节仍以 `docs/page-ui-specs/` 为真源；本目录维护验收用例 ID 与验收说明。

## 与 Gate 的关系

- `acceptanceTraceability` Gate 只校验用例定义、结构化绑定和代码位置，不执行测试。
- 修改本目录、Python/JUnit/Playwright 测试、marker/annotation 配置或映射实现时，
  `acceptanceTraceability` 由它自己的 `trigger.paths` 直接选中。
- 测试源码同时会触发它所属的 Pytest、Gradle 或 Playwright Gate；映射 Gate 不替代这些执行 Gate。
- TargetPreset 仅是人工调用的 Gate 分组；本目录不注册也不需要 `acceptance-cases` TargetPreset。
