# Feipi Session Browser — Agent 工程规则

- 中文沟通；标识符、命令、路径和 API 保持英文。先搜索定位，只读必要片段。不纳入真实 session、密钥、token、缓存、运行数据或个人配置。
- 普通说明、局部代码或样式小改由主线程直接做：说明用 `git diff HEAD --check -- <path>`（新文件直接审阅）；代码按[开发反馈表](docs/development/README.md#日常小改)运行最邻近的原生检查。无需 OpenSpec、委派或先跑整套 Gate。改 Java 时按需读取 `openspec/specs/java-code-conciseness/spec.md`。
- 非平凡产品、跨模块、agent、harness 或 Gate 契约变更走 OpenSpec skill。大型/独立工作按需委派，独立 QA 集中在交付点；先读共享 handoff 和 manifest，不复制协议或让多个 agent 重证同一小步。
- 原生子任务：模型路由、身份隔离和受保护路径以 `harness/agent-policy.manifest.yaml` 为准；用法和 Qoder 退役边界见 `docs/agent-runtime.md`。共用规则放 `skills/`、`harness/`，客户端只保留入口。
- 提交或交接前检查 diff，并显式运行整个待交付工作区的增量 Gate：`python3 scripts/gates/cli.py run --mode incremental`。局部反馈、人工 changed-files、旧 receipt 不替代交付。FAIL、BLOCKED、未运行或跳过均不得称 PASS，不新增 skip/skipif/fixme。
- 产品测试以最终 `javaBuildVerification` 根 `check` 的全模块测试与零跳过检查为准；未承接时运行 `./scripts/session-browser.sh test`，不重复运行已承接的检查。缓存命中不称测试重跑。改 build 配置另验 `java-build` target。
- 只在当前 checkout 工作；不回滚他人改动、不 stash/reset/force 或自动 commit/merge/push；不提交 ignored 文件，`openspec/changes/*` 不得 `git add -f`。
