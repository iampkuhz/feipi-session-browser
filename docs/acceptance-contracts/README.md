# 验收契约用例表

本目录是当前维护验收契约用例 ID 的标准位置。

历史上的 `docs/acceptance/` 与 `tests/acceptance/features/` 已不再作为维护位置；原有按功能域拆分的 markdown 表格恢复到本目录：

```text
docs/acceptance-contracts/
├── README.md
├── TEST_CONTRACT_ID_RULES.md
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

- 每个契约用例 ID 必须在 `features/*.md` 的“契约用例”表中定义。
- 每个 `features/*.md` 至少包含两个 markdown 表格：上方“范围”表和下方“契约用例”表。
- “契约用例”表格行必须包含用例 ID、优先级、分层、场景、怎么测、必须断言、测试类型、关联检查和代码位置。
- 测试里的 `@pytest.mark.contract_case(...)` marker 应能在本目录找到对应用例定义。
- 自动化用例的代码位置应指向真实测试文件；不再需要的用例应删除说明行，并同步删除对应测试绑定。
- 本目录不维护废弃用例信息；不要保留“已废弃/Deprecated/历史保留”说明。
- 页面行为细节仍以 `docs/page-ui-specs/` 为真源；本目录维护测试契约 ID 与验收说明。
