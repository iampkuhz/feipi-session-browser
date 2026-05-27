# 测试契约 ID 命名规则

## 总则

每个验收契约用例必须有唯一 ID，格式为：

```
{前缀}-{模块缩写}-{序号}
```

- 前缀：表示测试分层（DATA / UI / HOOK）
- 模块缩写：功能域标识（3-5 字符）
- 序号：三位数字，从 001 开始递增

示例：`DATA-SOURCE-001`、`UI-SESSIONS-001`、`UI-SD-001`

## 前缀列表

| 前缀 | 分层 | 说明 |
|---|---|---|
| **DATA** | data | 数据契约：数据源解析、索引、presenter 数据建模 |
| **UI** | visual / interaction | 视觉与交互契约：页面渲染、DOM 结构、交互行为 |
| **ROUTE** | data | 路由与 API 契约：HTTP 端点、模板渲染 |
| **HOOK** | data | Hook/Harness 契约：质量门禁、hook 策略 |

## 模块缩写

| 模块缩写 | 完整模块名 | 归属文件 |
|---|---|---|
| SOURCE | 数据源解析 | `features/DATA_SOURCES.md` |
| INDEX | 索引器 | `features/DATA_INDEX.md` |
| PRESENTER | Presenter 层 | `features/DATA_PRESENTERS.md` |
| DASHBOARD | Dashboard 页面 | `features/UI_DASHBOARD.md` |
| SESSIONS | 会话列表页 | `features/UI_SESSIONS_LIST.md` |
| SD | 会话详情页 | `features/UI_SESSION_DETAIL.md` |
| PROJECTS | 项目页（列表+详情） | `features/UI_PROJECTS.md` |
| AGENTS | Agent 页（列表+详情） | `features/UI_AGENTS.md` |
| GLOSSARY | 术语表页 | `features/UI_GLOSSARY.md` |
| VISUAL | 全局视觉契约 | `features/UI_GLOBAL_VISUAL.md` |
| INTERACTION | 跨页面交互 | `features/UI_INTERACTIONS.md` |
| HARNESS | Hook/Harness | `features/HOOK_HARNESS.md` |
| API | 路由与 API | `features/ROUTES_AND_API.md` |

## ID 绑定方式

### Playwright 标题绑定

Playwright 测试文件中的 `test('描述', ...)` 标题应包含契约 ID：

```js
test('DATA-SOURCE-001: Claude 会话解析返回 SessionSummary', async () => { ... });
```

如果测试覆盖多个用例 ID，用逗号分隔：

```js
test('UI-SD-003, UI-SD-004: 筛选功能', async () => { ... });
```

### pytest marker 绑定

pytest 测试函数使用 `@pytest.mark.contract` marker：

```python
@pytest.mark.contract("DATA-SOURCE-001")
def test_claude_parse_summary():
    ...
```

### 现有测试文件

现有测试文件未嵌入契约 ID 时，在 `ACCEPTANCE_CHECK_MATRIX.md` 中通过"关联测试"列建立映射，无需修改原测试文件。

## 硬规则

1. **ID 不可重复**：每个用例 ID 只能出现在一个契约行中
2. **序号不可跳跃**：同一模块缩写下，序号从 001 连续递增
3. **ID 不可复用**：删除用例后，其 ID 不再使用（标记为已废弃）
4. **优先级必填**：每个用例必须标注 P0/P1/P2
5. **分层必填**：每个用例必须标注 data/visual/interaction
6. **关联检查必填**：涉及截图的用例必须写 snapshot 更新条件
7. **代码位置必填**：必须标注关联的测试文件路径
