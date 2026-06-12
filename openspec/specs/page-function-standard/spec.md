# Page Function Standard Spec

## Requirements

### Requirement: Page behavior follows page-first UI specs

页面行为 SHALL 以 `docs/page-ui-specs/` 中的页面规约为真源，代码、模板、CSS、JS、测试和质量门必须对齐这些要求。

#### Scenario: Review page behavior

- **Given** 开发者需要确认页面行为
- **When** 读取仓库
- **Then** 优先查看 `docs/page-ui-specs/README.md`
- **And** 结合 `docs/page-ui-specs/common.md` 与对应 `docs/page-ui-specs/pages/*.md` 判断实现是否合规

### Requirement: UI specs stay page-first

页面细节 SHALL 按页面文件维护；跨页面要求 SHALL 只放在通用规约。

#### Scenario: Update UI requirements

- **Given** 开发者调整页面要求
- **When** 要求只影响单个页面
- **Then** 更新对应 `docs/page-ui-specs/pages/*.md`
- **And** 不把页面细节分散到主题型 contract 文件

### Requirement: Main navigation remains focused

Sidebar navigation SHALL include Dashboard, Sessions, and Projects. Single-agent profile analysis SHALL be reached from Dashboard agent scope.

#### Scenario: Define sidebar navigation

- **Given** 开发者修改 Sidebar
- **When** 调整导航项
- **Then** 不新增与当前页面结构无关的入口

### Requirement: Dashboard owns agent profile states

Dashboard SHALL be the target page for both all-agent overview and single-agent profile analysis.

#### Scenario: Review all-agent dashboard state

- **Given** agent scope is `All agents`
- **When** 开发者确认 Dashboard 行为
- **Then** Dashboard SHALL show global KPI, trend, token composition, cache health, agent contribution comparison, all agents summary, and agent/model efficiency
- **And** Dashboard SHALL NOT show `Hot Sessions & Signals`

#### Scenario: Review single-agent dashboard state

- **Given** agent scope is Claude Code, Qoder, or Codex
- **When** 开发者确认 Dashboard 行为
- **Then** Dashboard SHALL show KPI, trend, token composition, cache health, model mix, tool distribution, failure signals, model efficiency detail, and agent sessions for the selected agent
- **And** Dashboard SHALL NOT require a separate Agent Detail page for those fields

### Requirement: Session Detail has Trace and Payload main tabs only

Session Detail SHALL explain a single session's trace, payload, and attribution with exactly two main tabs: Trace and Payload.

#### Scenario: Define Session Detail tabs

- **Given** 开发者修改 Session Detail
- **When** 调整主 tab
- **Then** 页面 SHALL expose Trace and Payload as the only main tabs
- **And** request/response attribution SHALL be accessible from Trace round/subround rows and remain part of Payload call detail

### Requirement: List pages preserve complete user operations

Sessions, Projects, and project-level sessions tables SHALL preserve search, filtering, sorting, pagination, row navigation, and core fields.

#### Scenario: Reorganize a list page

- **Given** 开发者调整列表页
- **When** 重组字段、控件、列宽中的任一项
- **Then** UI MAY reorganize information
- **And** UI SHALL NOT reduce visible or operable information
- **And** constrained layouts SHALL use horizontal scrolling, truncation, and tooltip
- **And** constrained layouts SHALL NOT allow text overlap
