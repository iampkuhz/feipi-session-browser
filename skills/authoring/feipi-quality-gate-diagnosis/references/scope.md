## 负责范围

- Required quality gate 失败后的诊断和最小修复。
- Doctor 脚本（`scripts/harness/doctor.sh`）失败后的诊断。
- Java gates（编译、测试、PMD）失败后的诊断。
- UI gates（静态检查、JS action handler 检查）失败后的诊断。
- Agent policy、skill registry、OpenSpec 与 minimal harness 检查失败后的诊断。
- 判断失败类别并选择对应修复策略。
- 确保不把 skipped/未运行/环境受限描述为 PASS。

## 禁止范围

- 不改功能开发前置设计（应使用对应功能 skill）。
- 不改 OpenSpec 编排（应使用 `feipi-openspec-orchestrate-change`）。
- 不改产品代码逻辑（Java、Python 产品功能），除非是 gate 失败的最小修复。
- 不重新引入平台 Hook、Session Runtime 或自动 Git mutation。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不删 required gates。
- 不新增 skip（`pytest.skip`、`pytest.mark.skip`、`test.skip()` 等）。
- 不伪造 PASS 结果。
- 不安装依赖或修改运行环境。

## 关键路径

1. `scripts/gates/cli.py` → 唯一 Gate CLI；内部模块不得直跑。
2. `scripts/checks/<domain>/*.py` → 领域检查器，只按失败报告做精确 rerun。
3. `scripts/harness/doctor.sh` → 环境体检脚本。
4. `harness/skill-registry.yaml` → skill 注册表。
5. `harness/manifest.yaml` 与 `harness/agent-policy.manifest.yaml` → minimal harness 真相。
6. `shared check `agent.entry-parity`` → agent 入口 parity 检查。
7. `skills/authoring/<skill-name>/SKILL.md` → 各 skill 源文件。
8. `.claude/agents/*.md`、`.codex/agents/*.toml` → agent 入口文件。

## 常见误区

- 误以为可以直接跳过失败的 gate。实际必须诊断和修复，不能 skip。
- 误以为环境缺失时可以伪造 PASS。实际必须报告 BLOCKED。
- 误以为可以大范围重构来修复 gate 失败。实际只做最小修复。
- 误以为 gate 失败一定是代码问题。实际可能是 fixture 缺失、配置漂移或 gate 本身 bug。
- 误以为修完失败 gate 就结束。实际还要重跑 required baseline 确认无回归。
- 误以为未运行的 gate 可以计为 PASS。实际必须写明未运行原因。

## 触发门禁

- `python3 -m scripts.checks agent.skill-registry`
- `python3 -m scripts.checks agent.entry-parity`
- `python3 -m scripts.checks agent.rules-sync`
- `bash scripts/harness/doctor.sh`
- `python3 scripts/gates/cli.py --tier required`
