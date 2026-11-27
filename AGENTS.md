# Feipi Session Browser — Agent 工程规则

- 每次汇报先读并执行 $feipi-interaction-review-output 的 SKILL.md。
- 中文沟通；标识符、命令、路径和 API 用英文。先定位再最小读取。真实 session 等敏感数据不得入仓；授权本机核对按[隐私规则](skills/authoring/feipi-privacy-redaction-dev/references/redaction-policy.md#本机原文核对)。
- 开发、构建、验证与产品运行只支持 Apple Silicon macOS（arm64）；不要保留或新增其他平台的兼容分支、launcher、产物和对应测试。
- 每次发布使用全新索引目录，从原始会话源重新扫描构建；索引与运行状态不跨版本复用。不实现旧索引迁移、旧版回滚或跨版本兼容，不读取、迁移或删除旧索引作为发布步骤。保留当前会话源解析、安全校验与同版本正常增量扫描。
- 正式发布先把发行提交合入远端 `main`，再从该提交创建版本 tag；不从尚未合入的分支发布，也不移动已经推送的发布 tag。
- 小改主线程直接做，不用 OpenSpec 或委派。说明跑 `git diff HEAD --check -- <path>`（新文件直接审阅），代码按[开发反馈表](docs/development/README.md#日常小改)快验。Java 按需读 `openspec/specs/java-code-conciseness/spec.md`。
- 非平凡产品、跨模块、agent、harness 或 Gate 契约变更走 OpenSpec skill。复杂任务或单次多任务须拆给不同原生 subagent；先读共享 handoff 和 manifest，集成交付时集中 QA。
- 原生子任务的模型、身份和保护路径见 `harness/agent-policy.manifest.yaml`；用法及 Qoder 退役见 `docs/agent-runtime.md`。共享规则放 `skills/`、`harness/`，客户端只留入口。
- Codex 版本协作见 [Multica](docs/development/multica.md)。
- 按[修复闭环](skills/authoring/feipi-quality-gate-diagnosis/references/repair-loop.md)自行复核、修复、复测；必验全过才交付，尚未定位先自查，确无可行路径才报阻塞。
- 提交或交接前检查 diff，并显式运行整个待交付工作区的增量 Gate：`python3 scripts/gates/cli.py run --mode incremental`。局部反馈、旧 receipt 不替代交付。FAIL、BLOCKED、未运行或跳过均不得称 PASS，不新增 skip/skipif/fixme。
- 产品测试以最终 `javaBuildVerification` 根 `check` 的全模块测试与零跳过检查为准；未承接时运行 `./scripts/session-browser.sh test`，不重复运行已承接的检查。缓存命中不称测试重跑。改 build 配置另验 `java-build` target。
- 只在当前 checkout 工作；不回滚他人改动、不 stash/reset/force 或自动 commit/merge/push；不提交 ignored 文件，`openspec/changes/*` 不得 `git add -f`。
