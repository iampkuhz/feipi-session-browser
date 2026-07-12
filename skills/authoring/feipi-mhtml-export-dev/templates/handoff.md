## Goal

<一句话描述本次 MHTML 导出开发目标>

## Allowed scope

- 允许修改的文件列表：
  - `src/session_browser/web/mhtml.py` — 导出后端入口
  - `java/web/src/main/resources/templates/` — 导出相关 Jinja 模板
  - `java/web/src/main/resources/static/` — 需要内联的 CSS/JS 资源
  - `tests/backend/test_mhtml_export.py` — 导出测试
  - `scripts/checks/` — 导出相关检查脚本（如需）

## Forbidden scope

- 不改 session detail 页面的常规 UI（不涉及导出）。
- 不改后端 parser 代码。
- 不改 Java 产品代码。
- 不改 hooks、非导出相关的 quality gate 脚本。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不在导出文件中引入外部网络依赖。
- 不删 required gates。
- 不新增 skip。

## Required reading

- `skills/authoring/feipi-mhtml-export-dev/references/export-contract.md` — 导出契约。
- `skills/authoring/feipi-mhtml-export-dev/references/offline-resource-contract.md` — 离线资源契约。
- `skills/authoring/feipi-mhtml-export-dev/references/security-contract.md` — 安全脱敏契约。
- 导出入口和后端接口 — 只读与当前变更直接相关的部分。

## Validation

```bash
python scripts/checks/check_session_detail_static.py
python scripts/checks/check_js_action_handlers.py
```

按需追加：

```bash
pytest tests/backend/test_mhtml_export.py
```

## Expected output

- 改动的导出功能、模板、内联资源文件列表。
- 内联资源完整性说明。
- 离线交互保真风险评估。
- 敏感字段脱敏状态。
- 门禁运行结果。
- 导出文件大小和性能影响。
- 后续风险或 TODO。
