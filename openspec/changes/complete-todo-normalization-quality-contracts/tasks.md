# Tasks: Complete TODO normalization quality contracts

- [x] 1. 补齐 OpenSpec change 与 active context。
  - Validation: `python3 scripts/openspec/validate_layout.py && python3 scripts/openspec/validate_active_change.py --change-id complete-todo-normalization-quality-contracts`

- [x] 2. 实现 normalized artifact 结构化类型和 snake_case canonical JSON。
  - Validation: `./gradlew :java:artifact-normalized:test :java:normalization-engine:test --no-daemon`

- [x] 3. 实现 Codex child rollout subagent 归属。
  - Validation: `./gradlew :java:source-codex:test :java:normalization-engine:test --no-daemon`

- [x] 4. 修复 session samples 集成测试并接入质量门。
  - Validation: `./gradlew :java:contract-tests:test :java:contract-tests:sampleIntegrationTest --no-daemon`

- [x] 5. 完成 Python runtime、warning-free 和中文注释门禁。
  - Validation: `.venv/bin/python scripts/harness/python_env.py check-locks && bash scripts/harness/doctor.sh && .venv/bin/python scripts/quality/check_code_comment_language.py --script-comments scripts .claude/hooks .codex/hooks .qoder/hooks --policy config/technical-terms.json`

- [x] 6. 更新 TODO 并运行 required gates 收口。
  - Validation: `python3 scripts/quality/run_required_quality_gates.py --tier required --change-id complete-todo-normalization-quality-contracts`
