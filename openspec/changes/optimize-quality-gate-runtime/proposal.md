# Change: optimize quality gate runtime

## Problem

当前质量门禁在不同 agent 或 shell 环境下可能使用不同的 `python3`。当 `python3` 缺少项目依赖时，fixture server 会启动失败，但 `session-detail` 浏览器门禁仍继续运行，最终被 Playwright 超时拖慢。

## Proposed Changes

- 质量门运行器统一选择具备项目运行依赖的 Python。
- `pytest` gate 通过项目 Python 执行 `-m pytest`，避免依赖 PATH 中的 `pytest` shim。
- `./scripts/session-browser.sh test` 优先使用显式项目 Python、项目 venv 或可用的 Python 3 `python`。
- fixture server 启动失败时，依赖 fixture 的浏览器门禁立即返回 `BLOCKED`，不继续等待浏览器超时。
- `indexIntegrity` 直接运行时显式加入 `src/` import 路径。

## Success Criteria

- `index` target 不再因为 `session_browser` import 路径缺失而失败。
- `session-detail` target 在 fixture server 缺依赖或启动失败时快速失败，不再等待 Playwright 超时。
- 直接运行 `./scripts/session-browser.sh test` 不再错误回落到缺少 `pytest` 的 PATH `python3`。
- Claude Code、Codex、Qoder 经共享 stop runner 触发质量门时复用同一套运行器行为。
