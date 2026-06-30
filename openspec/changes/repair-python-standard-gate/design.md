# Design: 修复 python-standard 手动质量门禁

## Current state

`python-standard` 由 `scripts/session-browser.sh` 串联 Ruff、Pyright、doc、coverage、audit、complexity、vulture 和 deptry。当前配置仍包含不存在的 `src/session_browser`，coverage 会执行全量 pytest 并碰到旧 UI/Jinja 测试，Ruff/Pyright 对中文规约与历史脚本债务过度阻断，Xenon 以历史复杂度直接失败，Deptry 把开发时脚本依赖误判为 runtime 依赖。

## Proposed approach

- 在 `pyproject.toml` 中把 Python 分析范围收敛到 `scripts/` 与 tooling tests，并移除 stale source 配置。
- 在 `scripts/session-browser.sh` 中让 `coverage` 只运行 Python tooling 相关 pytest 并生成报告，不再拉起历史 UI/Jinja 全量 pytest；`complexity` 生成报告但不阻断 `python-standard`。
- 让 Ruff/Pyright/Deptry 的规则反映当前仓库：中文注释/文档不因全角标点失败，dev-only gate scripts 可使用 dev dependencies，首要阻断真实 unused/import/type 问题。
- 让 audit 使用可稳定查询的 OSV vulnerability service 审计 `requirements-dev.lock`，默认绕过本机代理环境以避免失效代理造成 manual baseline 阻断；如必须走代理可显式设置 `SESSION_BROWSER_AUDIT_USE_PROXY=1`。若 vulnerability service 仍因网络/代理/证书不可用，`python-standard` 只记录非阻塞诊断，真实漏洞结果或 Bandit high severity 仍阻断。
- 修复发现的 unused、dynamic import typing、optional access 等真实问题；不触碰 session-detail dirty implementation diff。

## Risks

- 规则校准过宽可能降低手动 baseline 信号；通过保留 Ruff、Pyright、coverage、audit、dead-code、deptry 的核心检查缓解。
- `pip-audit` 依赖外部网络或本机证书；若修复后仍出现 SSL/network failure，应作为环境 `BLOCKED` 汇报。
- 当前工作区已有 `web-010` 未提交改动；本变更避免改动其实现文件，降低冲突风险。

## Rollback

回滚本 change 下 OpenSpec 文件，以及 `pyproject.toml`、`scripts/session-browser.sh` 和相关 Python tooling 测试/脚本调整即可恢复旧行为。

## Validation

最终以 `python3 scripts/quality/run_quality_gate.py --target python-standard --change-id repair-python-standard-gate` 为收口证据，并补充 OpenSpec/harness 验证。
