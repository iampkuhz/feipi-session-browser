## 负责范围

- Required quality gate 失败后的诊断和最小修复。
- Doctor 脚本（`scripts/harness/doctor.sh`）失败后的诊断。
- Stop check 失败后的诊断。
- Java gates（编译、测试、PMD）失败后的诊断。
- UI gates（静态检查、JS action handler 检查）失败后的诊断。
- Agent runtime gates（entry parity、hook parity、policy sync、skill registry、manifest）失败后的诊断。
- 判断失败类别并选择对应修复策略。
- 确保不把 skipped/未运行/环境受限描述为 PASS。

## 禁止范围

- 不改功能开发前置设计（应使用对应功能 skill）。
- 不改 OpenSpec 编排（应使用 `feipi-openspec-orchestrate-change`）。
- 不改产品代码逻辑（Java、Python 产品功能），除非是 gate 失败的最小修复。
- 不改 hooks 脚本逻辑，除非 gate bug 定位到 hook。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不删 required gates。
- 不新增 skip（`pytest.skip`、`pytest.mark.skip`、`test.skip()` 等）。
- 不伪造 PASS 结果。
- 不安装依赖或修改运行环境。

## 关键路径

1. `scripts/quality/*.py` → 所有 quality gate 脚本。
2. `scripts/harness/doctor.sh` → 环境体检脚本。
3. `harness/skill-registry.yaml` → skill 注册表。
4. `harness/agent-runtime.manifest.yaml` → agent runtime manifest。
5. `scripts/quality/check_agent_entry_parity.py` → agent 入口 parity 检查。
6. `skills/authoring/<skill-name>/SKILL.md` → 各 skill 源文件。
7. `.claude/agents/*.md`、`.codex/agents/*.toml` → agent 入口文件。

## 常见误区

- 误以为可以直接跳过失败的 gate。实际必须诊断和修复，不能 skip。
- 误以为环境缺失时可以伪造 PASS。实际必须报告 BLOCKED。
- 误以为可以大范围重构来修复 gate 失败。实际只做最小修复。
- 误以为 gate 失败一定是代码问题。实际可能是 fixture 缺失、配置漂移或 gate 本身 bug。
- 误以为修完失败 gate 就结束。实际还要重跑 required baseline 确认无回归。
- 误以为未运行的 gate 可以计为 PASS。实际必须写明未运行原因。

## 触发门禁

- `python scripts/quality/check_skill_registry.py`
- `python scripts/quality/check_agent_runtime_manifest.py`
- `python scripts/quality/check_agent_entry_parity.py`
- `python scripts/quality/check_agent_hook_parity.py`
- `python scripts/quality/check_agent_rules_sync.py`
- `bash scripts/harness/doctor.sh`
