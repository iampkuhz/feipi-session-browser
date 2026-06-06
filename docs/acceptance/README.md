# 验收契约体系

> 本文档定义 Feipi Session Browser 的验收契约（Acceptance Contract）体系。

## 目的

本体系将 130+ pytest 文件和 7 个 Playwright 文件中的测试用例，按功能域分层组织为可追踪的**行为契约文档**。每个契约用例有唯一 ID，与源码和测试文件双向绑定。

## 三层测试模型

本体系采用三层测试模型，每层对应不同的质量风险：

| 分层 | 名称 | 覆盖内容 | 测试类型 |
|---|---|---|---|
| **data** | 数据契约 | 数据源解析、索引构建、presenter 数据建模、API 端点输出 | pytest 为主 |
| **visual** | 视觉契约 | 模板结构渲染、CSS 样式、多视口截图、DOM 布局契约 | Playwright + pytest |
| **interaction** | 交互契约 | 筛选/排序/分页、tab 切换、弹窗、键盘操作、跨页面导航 | Playwright 为主 |

### 分层判定规则

- **data**：不依赖浏览器，断言数据结构/字段/数值正确性
- **visual**：断言 DOM 结构可见性、CSS 样式属性、截图对比
- **interaction**：断言用户操作后的页面状态变化（URL 变化、DOM 显隐、样式切换）

## 文档结构

```
docs/acceptance/
├── README.md                        ← 本文件
├── ACCEPTANCE_CHECK_MATRIX.md       ← 总矩阵表（所有用例 ID 一览）
├── PAGE_ACCEPTANCE_CHECKLIST.md     ← 页面功能标准 v3 逐页验收清单
├── TEST_CONTRACT_ID_RULES.md        ← 测试 ID 命名规则
├── features/
│   ├── DATA_SOURCES.md              ← 数据源模块（Claude/Codex/Qoder 解析器）
│   ├── DATA_INDEX.md                ← 索引模块（SQLite 索引器、扫描器）
│   ├── DATA_PRESENTERS.md           ← Presenter 层（数据→视图模型）
│   ├── ROUTES_AND_API.md            ← 路由与 API 端点
│   ├── UI_DASHBOARD.md              ← Dashboard 页面
│   ├── UI_SESSIONS_LIST.md          ← Sessions List 页面
│   ├── UI_SESSION_DETAIL.md         ← Session Detail 页面
│   ├── UI_PROJECTS.md               ← Projects 页面（列表 + 详情）
│   ├── UI_AGENTS.md                 ← Agents 页面（列表 + 详情）
│   ├── UI_GLOSSARY.md               ← Glossary 页面
│   ├── UI_GLOBAL_VISUAL.md          ← 全局视觉契约（视口、Shell、基础组件）
│   ├── UI_INTERACTIONS.md           ← 跨页面交互（侧边栏、分页、AJAX）
│   └── HOOK_HARNESS.md              ← Hook/Harness 质量门禁
└── generated/
    ├── TEST_CONTRACT_COVERAGE.md    ← 运行 validate_test_contract_mapping.py 生成
    └── ORPHAN_TESTS.md              ← 运行 validate_test_contract_mapping.py 生成
```

## 页面功能标准 v3

当前页面功能标准要求见 `docs/ui/contracts/03-page-contracts.md`，逐页验收清单见 `PAGE_ACCEPTANCE_CHECKLIST.md`。

该标准收敛了旧版页面口径：

- Sidebar 主导航只包含 Dashboard、Sessions、Projects。
- 不提供独立 Agents 列表页；Agent 列表信息在 Dashboard，深度信息在 Agent Detail。
- Session Detail 只保留 Trace / Payload 两个主 tab。
- 列表页必须保留搜索、过滤、排序、分页和核心字段，不允许为视觉重排删减可见/可操作信息。

## 如何使用

### 添加新测试用例

1. 确定用例归属的功能域 → 选择 `features/` 下对应 md
2. 按 ID 规则分配用例 ID（参见 `TEST_CONTRACT_ID_RULES.md`）
3. 在对应的"契约用例"表中新增一行
4. 更新 `ACCEPTANCE_CHECK_MATRIX.md` 总矩阵

### 运行质量门禁

```bash
# 验证文档结构完整
python3 scripts/harness/validate_openspec_layout.py

# 运行产品测试
./scripts/session-browser.sh test

# 运行 Playwright E2E
npx playwright test
```

### 优先级定义

| 优先级 | 含义 | 示例 |
|---|---|---|
| **P0** | 核心路径不可断 | 会话解析、索引构建、页面加载 |
| **P1** | 重要功能 | 筛选/排序、tab 切换、多视口 |
| **P2** | 边界/增强 | 异常检测、性能基线、无障碍 |
