# CSS 加载与所有权要求

## 加载顺序

页面 CSS 按以下顺序加载：

1. `tokens.css`
2. `base.css`
3. `shell.css`
4. `ui-primitives.css`
5. 页面专属 CSS

## 所有权

- `tokens.css` 只维护设计变量。
- `base.css` 只维护基础元素、reset、typography 和 focus。
- `shell.css` 只维护整体壳层布局。
- `ui-primitives.css` 维护共享组件。
- 页面专属 CSS 只维护页面布局和页面特有组合。

## 禁止项

- 页面 CSS 不直接重写共享组件的基础定义。
- 不新增版本化 CSS 文件名。
- 不新增 patch、fix、overlay 或别名 CSS 文件。
- 不用空 selector、隐藏 selector 或别名 selector 支撑当前 UI。
- 不在 CSS 中保留来源行号或阶段注释。

## 桌面视口

- 当前 UI 只维护桌面端视口。
- CSS 可以维护宽屏和桌面收敛规则。
- 不维护移动端或平板专属断点。
