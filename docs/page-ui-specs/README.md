# 页面 UI 规约入口

本目录是页面 UI 规约真源。通用要求放在 `common.md`，每个页面的完整细节放在 `pages/`，快速验收放在 `page-acceptance-checklist.md`。

不放在 `harness/`：`harness/` 只承载 agent 工作流、上下文包和验证入口；页面布局、文案、数据口径和交互行为属于产品 UI 规约。

## 目标页面

- `pages/01_dashboard.md`：Dashboard，全局和单 agent 范围概览。
- `pages/02_sessions.md`：Sessions，session 检索、过滤、排序、分页和行跳转。
- `pages/03_session_detail.md`：Session Detail，单 session 的 Trace、Payload 和 attribution。
- `pages/04_projects.md`：Projects，项目列表和项目级统计入口。
- `pages/05_project_detail.md`：Project Detail，单项目统计和项目内 sessions。
- `pages/07_token_glossary.md`：Token Glossary，术语、token 口径和 provider 映射。
- `pages/08_state_pages.md`：404、Error、空态等状态页。

## 非目标页面

- 目标结构不提供独立 Agents 列表页；agent 汇总和单 agent 深度信息都放到 Dashboard。
- Sidebar 主导航目标只保留 Dashboard、Sessions、Projects；Glossary 可作为辅助入口但不作为核心业务导航。

## 使用方式

- 改某个页面前，先读 `common.md` 和对应页面文件。
- 改共享组件、壳层、CSS import、状态页、质量门时，先读 `common.md`。
- 页面文件统一按定位、页面布局、控件和候选项、文字内容、数据指标与口径、交互逻辑、状态、禁止项组织。
- 代码、模板、CSS、JS、测试和质量门与本目录冲突时，先判断真源，再更新实现和规约中需要变更的部分，不允许长期分叉。
