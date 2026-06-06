# Page Function Standard Spec

## Requirements

### Requirement: Page behavior follows docs/ui requirements

页面行为 SHALL 以 `docs/ui/` 中的页面功能要求为真源，代码、模板、CSS、JS、测试和质量门必须对齐这些要求。

#### Scenario: Review page behavior

- **Given** 开发者需要确认页面行为
- **When** 读取仓库
- **Then** 优先查看 `docs/ui/contracts/03-page-contracts.md`
- **And** 结合 `docs/ui/contracts/` 与 `docs/ui/design/` 下的细分要求判断实现是否合规

### Requirement: Main navigation remains focused

Sidebar navigation SHALL include Dashboard, Sessions, and Projects. Agent Detail SHALL be reached from Dashboard agent rows or detail selectors.

#### Scenario: Define sidebar navigation

- **Given** 开发者修改 Sidebar
- **When** 调整导航项
- **Then** 不新增与当前页面结构无关的入口

### Requirement: Session Detail has Trace and Payload main tabs only

Session Detail SHALL explain a single session's trace, payload, and attribution with exactly two main tabs: Trace and Payload.

#### Scenario: Define Session Detail tabs

- **Given** 开发者修改 Session Detail
- **When** 调整主 tab
- **Then** 页面 SHALL expose Trace and Payload as the only main tabs
- **And** request/response attribution SHALL be part of Payload call detail

### Requirement: List pages preserve complete user operations

Sessions, Projects, and project-level sessions tables SHALL preserve search, filtering, sorting, pagination, row navigation, and core fields.

#### Scenario: Reorganize a list page

- **Given** 开发者调整列表页
- **When** 重组字段、控件或列宽
- **Then** UI MAY reorganize information
- **And** UI SHALL NOT reduce visible or operable information
- **And** constrained layouts SHALL use horizontal scrolling, truncation, and tooltip
- **And** constrained layouts SHALL NOT allow text overlap
