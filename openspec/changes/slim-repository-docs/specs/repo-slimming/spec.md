# 规格增量：仓库文档瘦身

## Requirement: Repository documentation is current-state only

仓库文档 SHALL 只描述当前代码、当前规约和当前验证入口。

### Scenario: Historical change records are not maintained as source files

- **Given** 开发者需要理解当前行为
- **When** 读取仓库规约
- **Then** 应从 `openspec/specs/`、`AGENTS.md`、`CLAUDE.md`、`README.md` 和当前变更目录获取信息
- **And** 不需要读取历史版本 change 文档

## Requirement: UI requirements are maintained under docs/page-ui-specs

`docs/page-ui-specs/` SHALL describe page functionality requirements that code must follow.

### Scenario: Review UI requirements

- **Given** 开发者修改页面功能、模板、CSS 或 JS
- **When** 判断目标行为
- **Then** 应先读取 `docs/page-ui-specs/README.md`
- **And** 根据 `docs/page-ui-specs/common.md` 与对应 `docs/page-ui-specs/pages/*.md` 实现和验证

## Requirement: Harness documentation is minimal

harness SHALL 通过 manifest、脚本和少量入口文档描述当前执行方式。

### Scenario: Quality rules use executable sources

- **Given** 质量门已有脚本和测试实现
- **When** 维护门禁
- **Then** 以脚本、测试和 `harness/manifest.yaml` 为真源
- **And** 不维护重复的人工矩阵或历史诊断手册
