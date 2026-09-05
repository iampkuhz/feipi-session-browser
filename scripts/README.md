# Scripts 中文维护地图

公开命令以 `harness/manifest.yaml` 为机器真相。日常只需要两个入口：

```bash
./scripts/session-browser.sh <command>
python3 scripts/gates/cli.py run --mode incremental
```

Gate 的完整中文手册是 `docs/gates/gate-control-plane.md`；机器声明按业务位于
`scripts/gates/catalog/domains/`，由 `catalog/registry.py` 汇总为唯一 Catalog。

## 从外到内只看三层

1. **产品开发：** 使用 `session-browser.sh` 的 `deps|test|scan|serve|stop|status|doctor|version|help`。
2. **交付验证：** 使用 `gates/cli.py run --mode incremental`；需要单项诊断时先用 `list/explain/plan`。
3. **基础设施维护：** 只有修改 Gate、Harness、OpenSpec 或 Release 本身时才进入对应目录。

## 一级目录按业务归属

```text
scripts/
├── session-browser.sh        产品/本地开发入口，业务命令透传 Java CLI
├── gates/                    Gate 分阶段控制面与 Python Check
│   ├── cli.py                唯一公开 Gate CLI
│   ├── catalog/              contracts、registry、validation、业务声明
│   ├── planning/             输入快照、Trigger 匹配、GatePlan
│   ├── execution/            命令适配、进程监督、结果分类、运行编排
│   ├── evidence/             immutable schema v5 receipt
│   ├── presentation/         human/JSON 输出与终端事件
│   ├── maintenance/          health audit
│   ├── checks/               只能用 Python 表达的领域检查
│   │   ├── agent/            Agent、权限、Skill 与交接协议
│   │   ├── privacy/          secret、真实 Session 与本地路径保护
│   │   ├── repository/       Git、公开入口、测试、fixture 与验收映射
│   │   └── source/           注释与语言政策
├── harness/                  只读 doctor、项目 Python 和 Harness 结构验证
├── openspec/                 change 创建与 OpenSpec validators
└── release/                  release candidate、checksum 和升级/回滚演练
```

`checks/` 属于 Gate，所以不再与 `gates/` 平铺。JVM/Web resource 规则位于
`java/tests/quality-gates/`，由 Java owner 实现；Python Check 不复制一套。

## 一屏调用链

```text
gates.cli
  → catalog（TargetPreset、Trigger、唯一 recipe）
  → planning（ChangeSnapshot / TriggerMatch / GatePlan）
  → execution（依次运行 RecipeStep）
      python-check → 内部 gates.checks 适配器 → registry → 唯一 check()
      java-rule    → Gradle → QualityGateCli → 唯一 Java rule
      gradle-task  → 对应 Gradle task
      command / playwright / scan-smoke → 固定外部工具或 suite
  → evidence / presentation（RunReceipt 与 PASS / BLOCKED / FAIL）
```

阶段只允许正向依赖；Maintenance 只经公开契约审计。不要再新增 `model.py`、`support.py`、`utils.py`、
第二份 registry、跨阶段 helper 或只转发一次的 wrapper。

## 到哪里修改

| 需求 | 唯一入口 | 同批验证 |
|---|---|---|
| 修改 Gate 的 Trigger、TargetPreset、recipe 或时间目标 | `scripts/gates/catalog/domains/` | catalog、plan/explain、Trigger characterization |
| 修改 Python 领域规则 | `scripts/gates/checks/<domain>/check_*.py` | registry 与对应 `scripts/tests/checks/` |
| 修改 Java/Web resource 规则 | `java/tests/quality-gates/` | 对应 Java test 与 Gate |
| 修改普通 Gradle 检查 | 对应 `java/build.gradle.kts` 或 build logic | 对应 task 与 `java-build` TargetPreset |
| 修改计划、执行或状态归约 | `scripts/gates/{planning,execution,evidence,presentation}/` | 对应职责命名的 `scripts/tests/gates/` |
| 修改 Python 环境或 Harness 结构 | `scripts/harness/` | `scripts/tests/harness/`、doctor |
| 修改 OpenSpec 结构 | `scripts/openspec/` | 三个 OpenSpec validator |
| 修改发布流程 | `scripts/release/`、`.github/workflows/release.yml` | shell syntax、release contract |

## 状态定位

| 现象 | 含义 | 先看 |
|---|---|---|
| `NOT_TRIGGERED` | incremental 路径没有选中 Gate | Catalog Trigger 和 `plan` 的匹配理由 |
| `BLOCKED` | 检查完成并确认仓库存在问题 | RunReceipt 的 Gate/RecipeStep 诊断 |
| `FAIL` | 检查没有完成或无法判断 | reason、owner、process supervisor |
| Python Check 失败 | 一个 Check ID 返回问题 | `checks/check_registry.py` 和唯一 `check_*.py` |
| Java rule 失败 | 一个 Java rule ID 返回问题 | `QualityGateCli` registry 和唯一 `*Rule.java` |

文件浏览器中的 `__pycache__/`、`*.pyc` 和任意层级 `.local/` 都是忽略的本地内容；真实源码清单以
`git ls-files scripts` 为准。移动入口时同步实现、声明、测试、文档和直接 caller，删除旧路径，不留 alias。
