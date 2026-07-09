## 负责范围

- Session detail 页面的 MHTML / 自包含 HTML 导出功能。
- CSS/JS/图片/字体等静态资源的内联处理。
- 离线打开后的交互保真（tabs、modal、collapse、trace 展开等）。
- Current-session tab 在导出文档中的行为。
- 导出文件中的敏感字段脱敏策略。
- 导出相关的 fixture-based 测试。
- 导出文件大小和性能上限管理。

## 禁止范围

- 不改 session detail 页面的常规 UI（不涉及导出的部分）。
- 不改后端 parser 代码（Claude Code / Codex / Qoder parser）。
- 不改 Java 产品代码（core-domain、sources、index-sqlite 等模块）。
- 不改 OpenSpec 编排或 agent runtime 配置。
- 不改 session ingestion pipeline 或 token attribution 逻辑。
- 不改 hooks、非导出相关的 quality gate 脚本。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不在导出文件中引入外部网络依赖（CDN、Google Fonts 等）。

## 关键路径

1. `src/session_browser/web/mhtml.py` → 导出后端入口。
2. `java/web/src/main/resources/templates/` → 导出相关 Jinja 模板。
3. `java/web/src/main/resources/static/` → 需要内联的 CSS/JS 资源。
4. `tests/backend/test_mhtml_export.py` → 导出功能测试。
5. `references/export-contract.md` → 导出契约。
6. `references/offline-resource-contract.md` → 离线资源契约。
7. `references/security-contract.md` → 安全脱敏契约。

## 常见误区

- 误以为可以直接引用 CDN 资源。实际所有资源必须内联，禁止外部网络请求。
- 误以为导出文件不需要交互保真。实际 tabs/modal/collapse 等关键交互在离线打开时必须可用。
- 误以为敏感字段可以原样导出。实际必须遵循 UI 当前脱敏状态或显式导出策略。
- 误以为可以用真实 session 数据做导出测试。实际必须使用 fixture 或 mock 数据。
- 误以为导出文件不需要大小限制。实际必须有上限说明和降级策略。
- 误以为只改后端不影响 UI gate。实际导出模板变更可能影响 session detail 静态检查。

## 触发门禁

- `python scripts/quality/check_session_detail_static.py`
- `python scripts/quality/check_js_action_handlers.py`
- fixture-based 导出测试
- `python scripts/quality/check_agent_entry_parity.py`
