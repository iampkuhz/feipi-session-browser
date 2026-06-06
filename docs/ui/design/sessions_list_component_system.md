# Sessions 列表组件要求

## 页面组成

- Page Head：标题、简短副标题、必要操作。
- Filter Card：搜索、agent、project、date、status、token 过滤。
- Active Filters：展示当前过滤项并可单项移除。
- Sessions Table：展示 session 记录。
- Pagination：展示页码、总数、page size、上一页、下一页。

## 表格列

- Title：主列，吸收宽屏空间。
- Project：项目名称或路径摘要。
- Agent：独立 agent badge。
- Model：model badge 或文本。
- Time：最近时间。
- Tokens：总量加 tokenbar。
- Status：失败或异常状态。

## Token Cell

- 左侧显示缩写 token 总量。
- 右侧 tokenbar 使用统一分类颜色。
- hover 展示分类明细 tooltip。
- tooltip 数值对齐。

## 行状态

- hover 高亮当前行。
- selected 或 active 行必须可区分。
- 行内操作不改变行高度。
- 长标题截断并提供完整 title 或 tooltip。
