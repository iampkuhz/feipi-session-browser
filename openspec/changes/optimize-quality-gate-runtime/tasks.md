# Tasks

## 1. Runner Runtime

- [x] 统一项目 Python 选择逻辑。
- [x] 将 Python gate 和 pytest gate 切到项目 Python。
- [x] 修复 `./scripts/session-browser.sh test` 的 Python 回退顺序。
- [x] 增加 fixture server 启动失败的 fail-fast 行为。

## 2. Index Gate

- [x] 修复直接运行 `indexIntegrity` 时的 `src/` import 路径。

## 3. Tests

- [x] 增加运行器单测覆盖项目 Python 和 fixture fail-fast。
- [x] 运行相关质量门禁并记录结果。
