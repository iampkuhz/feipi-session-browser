# 测试契约 ID 命名规则

## 总则

每个验收契约用例必须有唯一 ID，格式为：

```text
{前缀}-{模块缩写}-{序号}
```

- 前缀：表示测试分层或系统域。
- 模块缩写：功能域标识。
- 序号：三位数字，从 001 开始递增。

示例：`DATA-SOURCE-001`、`DATA-PRESENTER-006`、`UI-SD-001`。

## 前缀列表

| 前缀 | 分层 | 说明 |
|---|---|---|
| `DATA` | data | 数据契约：数据源解析、索引、presenter 数据建模 |
| `UI` | visual / interaction | 视觉与交互契约：页面渲染、DOM 结构、交互行为 |
| `ROUTE` | data | 路由与 API 契约：HTTP 端点、模板渲染 |
| `HOOK` | data | Hook/Harness 契约：质量门禁、hook 策略 |

## 模块缩写

| 模块缩写 | 完整模块名 | 归属文件 |
|---|---|---|
| `SOURCE` | 数据源解析 | `features/DATA_SOURCES.md` |
| `INDEX` | 索引器 | `features/DATA_INDEX.md` |
| `PRESENTER` | Presenter 层 | `features/DATA_PRESENTERS.md` |
| `DASHBOARD` | Dashboard 页面 | `features/UI_DASHBOARD.md` |
| `SESSIONS` | 会话列表页 | `features/UI_SESSIONS_LIST.md` |
| `SD` | 会话详情页 | `features/UI_SESSION_DETAIL.md` |
| `PROJECTS` | 项目页 | `features/UI_PROJECTS.md` |
| `GLOSSARY` | 术语表页 | `features/UI_GLOSSARY.md` |
| `VISUAL` | 全局视觉契约 | `features/UI_GLOBAL_VISUAL.md` |
| `INTERACTION` | 跨页面交互 | `features/UI_INTERACTIONS.md` |
| `HARNESS` | Hook/Harness | `features/HOOK_HARNESS.md` |
| `API` | 路由与 API | `features/ROUTES_AND_API.md` |

## 绑定方式

### pytest marker

pytest 测试函数使用 `contract_case` marker：

```python
@pytest.mark.contract_case("DATA-PRESENTER-006")
def test_round_signal():
    ...
```

如果测试覆盖多个用例 ID，可以传入多个参数：

```python
@pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
def test_pagination():
    ...
```

### Playwright 标题

Playwright 测试标题可以包含契约 ID：

```js
test('UI-SD-003: Trace tab can expand a round', async () => { ... });
```

## 硬规则

1. ID 不可重复：每个用例 ID 只能出现在一个契约行中。
2. ID 不可复用：删除用例后，其 ID 不再用于新含义。
3. 优先级必填：每个用例必须标注 P0/P1/P2。
4. 分层必填：每个用例必须标注 data/visual/interaction。
5. 代码位置必填：必须标注关联的测试文件或实现文件路径。
6. 测试代码中绑定的 ID 必须能在 `docs/acceptance-contracts/features/*.md` 中找到。
7. 不再需要的用例必须同时删除契约表格行和对应测试绑定；不得保留“已废弃/Deprecated/历史保留”说明。
