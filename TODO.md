# TODO

- [x] 完成版本发布流水线
- [ ] 配置 codex 使用 litellm 监控
- [ ] 分析为什么 claude code 不同 session 分析不出正确的 tool 候选是几个。怎么才能正确提取，并添加对应门禁
- [ ] 归因 modal UI 优化：指标里面文字被截断，要支持左右滑动；指标现在3个表格合并在一行，考虑合并成2个表格；归因弹框 modal 宽度优化，对于宽屏，增加宽度
- [ ] 产出完整的提取手册和规约，说明每个工具，是怎么处理流程（plantuml），以及怎么映射 token 归因的
- [ ] 案例 bug 分析： claudecode 的 session fae95c10-3dd4-4f01-a207-df0146fbab34 出现下述问题：
  - [ ] 没有正确判断出当前 llm call，到底用的是哪个 agent，当前这个 agent 到底会发几个 tools 信息