# Codex Prompt: session-browser 高保真 UI 改造任务生成

## 目标

请基于随附的高保真 HTML 样例，重写 `tools/session-browser` 的第二轮 UI 改造任务计划，并拆成几十个可串行执行的任务文件。不要直接改代码；先分析仓库，再生成任务文件。

## 随附高保真文件

- `hf_01_session_detail_mhtml_ready.html`：Session Detail 主页面。包含 Overview、Trace Workbench、Calls/Hotspots 子视图、Context Inspector。核心目标。
- `hf_02_sessions_list.html`：Sessions List 页面。用于 session triage。
- `hf_03_calls_view.html`：Calls View / LLM Call Index。替代原 Profile 的主能力。
- `hf_04_hotspots_view.html`：Hotspots 诊断聚合视图。
- `hf_05_full_payload_viewer.html`：Full Payload Viewer，用于长 request/response/raw JSON。
- `hf_00_gallery.html`：样例入口页。

## 设计原则

1. 默认浅色主题。
2. Overview 使用 `hf_01` 的结构和视觉效果，不要再压缩到难看。
3. Workbench 保持 compact：Trace 行默认单行；只展开当前 round；LLM/tool 子操作在 `span-list` 中展示；`.sk` 上下居中；Trace 视图不显示 Hotspots 内容。
4. `Trace / Calls / Hotspots` 是同一个 Session Detail 内的子视图：Trace = round/span tree；Calls = LLM call index；Hotspots = diagnostics projection；切换必须在导出的 MHTML 中仍可用。
5. Inspector 是 contextual，不是 session 全局信息。Overview 负责 session 全局；Inspector 负责当前选中对象。
6. 长 request/response/raw payload 不放进 Workbench，也不要塞满 Inspector；使用 Full Payload Viewer。
7. 左侧导航第一阶段只保留核心入口：Trace Workbench / Sessions / Projects / Agents。删除 Search、Glossary、左侧 Hotspots。
8. 顶部按钮职责：topbar = Map / Inspector / Focus；hero = Jump / Inspect anomaly；Workbench header = Failed only / High token / Open selected。

## MHTML 导出要求

Session Detail 页必须支持导出为单文件 MHTML，并且导出的 MHTML 在本地打开后仍能在当前 session 的子视图之间切换：

- Trace / Calls / Hotspots 切换必须可用；
- Inspector tab 切换必须可用；
- 左侧 Map、右侧 Inspector、Focus 模式的显示/隐藏必须可用；
- 不依赖后端 API、外部 CSS、外部 JS、远程字体、远程图片；
- 导出页面需要内联必要 CSS 和 JS；
- 页面数据应以内联 JSON 或服务端渲染 HTML 的形式写入；
- 导出 MHTML 不要求跨 session 导航可用，但当前 session 内部交互必须可用。

建议实现一个导出入口：

```text
GET /sessions/<agent>/<session_id>.mhtml
```

或：

```text
GET /sessions/<agent>/<session_id>?export=mhtml
```

可选实现路径：

- 由浏览器/Playwright/Chrome DevTools Protocol `Page.captureSnapshot` 生成 MHTML；
- 或通过 Chromium extension / `chrome.pageCapture.saveAsMHTML`；
- 或先生成完全自包含 HTML，再由外部保存为 MHTML。

## 必须拆分出的任务

至少生成以下任务文件：

1. 设计令牌与浅色主题收敛。
2. 三栏 Shell 布局稳定化：sidebar / main / inspector。
3. 左侧导航收敛：删除 Search / Glossary / Hotspots。
4. Overview 按高保真样例重构。
5. Workbench Header 重构：合并 `wb-title` 与 `wb-mode`。
6. Trace Tree Grid 实现。
7. Span List 子操作实现：圆点/连线/`.sk` 垂直居中。
8. Trace view 删除 Hotspots / round-summary。
9. Calls View 实现：LLM Call Index。
10. Hotspots View 实现：诊断投影。
11. Context Inspector 实现。
12. Full Payload Viewer 实现。
13. Payload Visibility Mismatch 数据与 UI。
14. Request Payload / Rendered Context / Response Payload 概念拆分。
15. MHTML-ready session page：内联 CSS/JS/data。
16. MHTML export route 或 export command。
17. MHTML 导出回归测试：本地打开后 Trace/Calls/Hotspots 可切换。
18. Playwright 截图或 DOM 校验。
19. 横向滚动阴影修复或移除。
20. 手工 QA checklist。

## 每个任务文件格式

请生成目录：

```text
tasks/ui-refactor-hifi/
  00-overview.md
  01-foundation/
  02-session-detail/
  03-workbench/
  04-inspector-viewer/
  05-mhtml-export/
  06-list-pages/
  07-validation/
```

每个任务文件必须包含：Goal / Background / Reference Hi-Fi File / Files to inspect / Files likely to change / Required changes / Validation script or test first / Acceptance criteria / Non-goals / Risks / Dependencies / Suggested execution command / Manual QA checklist。

## 输出要求

1. 先输出任务总表：`ID / File / Phase / Type / Priority / Depends On / Validation`。
2. 再逐个输出任务文件内容。
3. 每个任务必须足够小，适合一个 agent 单独执行。
4. 明确哪些任务只改 CSS，哪些改模板，哪些改 JS，哪些改后端导出，哪些改测试。
5. 不要直接开始改代码。
