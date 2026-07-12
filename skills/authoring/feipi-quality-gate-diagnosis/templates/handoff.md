## Goal

<一句话描述本次质量门诊断目标，例如"修复 skill registry gate 失败">

## Allowed scope

- 允许修改的文件列表：
  - `scripts/checks/<gate-script>.py` — 触发失败的 gate 脚本（如需修复 gate bug）
  - `harness/skill-registry.yaml` — registry 配置（如适用）
  - `harness/agent-runtime.manifest.yaml` — manifest 配置（如适用）
  - 其他与当前 gate 失败直接相关的文件（按需列出）

## Forbidden scope

- 不改产品代码逻辑（Java、Python 产品功能），除非是 gate 失败的最小修复。
- 不改 hooks 脚本逻辑，除非 gate bug 定位到 hook。
- 不改真实 session 数据、缓存、密钥、token、个人配置。
- 不删 required gates。
- 不新增 skip。
- 不伪造 PASS。
- 不安装依赖或修改运行环境。

## Required reading

- `skills/authoring/feipi-quality-gate-diagnosis/references/failure-diagnosis.md` — 失败诊断流程。
- `skills/authoring/feipi-quality-gate-diagnosis/references/gate-taxonomy.md` — gate 分类。
- 触发失败的 gate 脚本源码 — 只读与当前失败直接相关的部分。

## Validation

```bash
# 重跑触发失败的 gate
<失败的命令>

# 运行 required baseline
python scripts/checks/check_skill_registry.py
python scripts/checks/check_agent_runtime_manifest.py
bash scripts/harness/doctor.sh
```

## Expected output

- 失败 gate 名称和 exit code。
- 失败类别和最小修复内容。
- 重跑结果（PASS/FAIL/BLOCKED）。
- Required baseline 运行结果。
- 未运行的 gate 及原因。
- 后续风险或 TODO。
