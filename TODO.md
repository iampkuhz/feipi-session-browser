# TODO

- [ ] codex subagent 识别问题：http://127.0.0.1:18999/sessions/codex/019edb11-581d-7070-83c7-500239a85403
  - [ ] 提取原始信息到 docs/agent-token-attribution/ ，作为样例分析
- [ ] ./scripts/session-browser.sh test 出现 warning，后续添加门禁拒绝出现类似问题
- [ ] UI 优化：Context Budget 独占一行，Tool Impact 和 Issues & Repro Seeds 左右排列
- [ ] 当前仓库只声明最低 Python 版本和未锁定依赖，缺少本地/发布 venv 的 Python 版本、依赖锁定与质量门一致性校验，后续应独立建立 Python 环境契约并让 doctor 校验环境一致性而非仅检查 .venv 是否存在
- [ ] tests/session_detail/test_session_detail_page.py 中 class-scoped fixture 仍以实例方法定义，pytest 10 将移除该用法，后续应改为模块级 fixture 或明确的 classmethod fixture 以消除 PytestRemovedIn10Warning

- [x] 完成版本发布流水线
- [x] 配置 codex 使用 litellm 监控
- [x] 分析为什么 claude code 不同 session 分析不出正确的 tool 候选是几个。怎么才能正确提取，并添加对应门禁
- [x] 归因 modal UI 优化：指标里面文字被截断，要支持左右滑动；指标现在3个表格合并在一行，考虑合并成2个表格；归因弹框 modal 宽度优化，对于宽屏，增加宽度
- [x] 产出完整的提取手册和规约，说明每个工具，是怎么处理流程（plantuml），以及怎么映射 token 归因的
- [x] 案例 bug 分析： claudecode 的 session fae95c10-3dd4-4f01-a207-df0146fbab34 出现下述问题：
  - [x] 没有正确判断出当前 llm call，到底用的是哪个 agent，当前这个 agent 到底会发几个 tools 信息