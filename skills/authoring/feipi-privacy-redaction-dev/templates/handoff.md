## Goal

描述当前隐私脱敏任务的具体目标。说明哪些数据、文件或流程需要脱敏处理。

## Allowed scope

列出允许修改的文件或目录范围。典型范围：

- 涉及敏感字段的展示或导出代码。
- 测试 fixture 文件。
- 隐私 gate 脚本。
- 配置文件。

## Forbidden scope

列出禁止修改的文件或目录范围。典型禁止：

- 真实 session 数据。
- 产品脱敏逻辑（除非任务明确要求）。
- 平台 Hook 或 Session Runtime。
- 其他 skill 内容。

## Required reading

列出执行前必须读取的文件：

- `skills/authoring/feipi-privacy-redaction-dev/SKILL.md`
- `skills/authoring/feipi-privacy-redaction-dev/references/sensitive-fields.md`
- `skills/authoring/feipi-privacy-redaction-dev/references/redaction-policy.md`
- `skills/authoring/feipi-privacy-redaction-dev/references/fixture-policy.md`

## Validation

列出必须运行的验证命令：

- `python3 scripts/gates/cli.py run --mode incremental --gate testDataPrivacy`
- `python3 scripts/gates/cli.py run --mode incremental --gate credentialLeakScan`
- `python3 scripts/gates/cli.py run --mode incremental --gate governanceLayoutValidation`
- `python3 scripts/harness/validate_harness_structure.py`
- `bash scripts/harness/doctor.sh`

## Expected output

描述期望产物：

- 脱敏后的代码或配置变更。
- 隐私 gate 运行结果（PASS/FAIL）。
- 残留风险和后续 TODO。
