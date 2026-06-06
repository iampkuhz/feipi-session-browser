# Design

## Interpreter Selection

`scripts/quality/run_quality_gate.py` 负责统一选择质量门运行时使用的 Python。选择顺序以显式配置和项目本地环境优先：

- `SESSION_BROWSER_PYTHON`
- `SESSION_BROWSER_VENV_DIR/bin/python`
- `.venv/bin/python`
- 当前解释器
- PATH 中的 `python`
- PATH 中的 `python3`

候选解释器必须能导入项目运行依赖。`pytest` gate 还必须能导入 `pytest`。

`./scripts/session-browser.sh test` 使用同样的原则：优先 `SESSION_BROWSER_PYTHON` 和项目 venv；当本地没有 `.venv` 时，优先选择可用的 Python 3 `python`，避免直接落到缺少项目依赖的 PATH `python3`。

## Fixture Fail Fast

`browserLayout` 和 `browserInteraction` 依赖 HIFI fixture session。当默认 `BASE_URL` 不可用且临时 fixture server 启动失败时，运行器直接写入 `BLOCKED` gate detail，并保留启动失败摘要。

这样做保留了阻断能力，同时避免把环境依赖问题表现为 60 秒以上的 Playwright 超时。
