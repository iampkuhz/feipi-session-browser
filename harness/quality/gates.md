# Quality Gates

This document describes all quality gates for the feipi-session-browser repository.

## Gate Levels

### Level 1: Harness Structure

```bash
python3 scripts/harness/validate_harness_structure.py
```

Verifies that the harness directory structure and required files exist.

### Level 2: OpenSpec Layout

```bash
python3 scripts/harness/validate_openspec_layout.py
```

Validates the OpenSpec directory structure and schema compliance.

### Level 3: Marker Cleanup

```bash
python3 scripts/harness/check_no_unfinished_markers.py
```

Ensures no TODO, HACK, FIXME markers remain without tracking.

### Level 4: Task File Validation

```bash
python3 scripts/harness/validate_task_files.py
```

Validates that task files are well-formed and executable.

### Level 5: Repo Structure

```bash
python3 scripts/quality/validate_repo_structure.py
```

Deterministic check that command/skill/hook/spec structure is properly installed:
- `.claude/commands/change.md` exists.
- `.claude/skills/change/SKILL.md` exists.
- All hook scripts exist and are wired in `.claude/settings.json`.
- Default agents exist and reference active_change.
- Harness validation scripts exist.

### Level 6: Hook Self-Tests

```bash
python3 scripts/agent_hooks/guard_active_openspec_change.py --self-test
python3 scripts/agent_hooks/stop_validate_change.py --self-test
python3 scripts/agent_hooks/inject_session_context.py --self-test
python3 scripts/agent_hooks/log_change_evidence.py --self-test
```

Proves that hooks correctly handle positive and negative cases.

### Level 7: Doctor

```bash
bash scripts/harness/doctor.sh
```

Single-entry health check that runs all above gates.

## When to Run

| Event | Gates |
|-------|-------|
| After any harness change | Level 1-5 |
| Before session stop | Level 3 (via Stop hook) |
| Before commit | Level 1-5 |
| After repo migration | Level 1-7 |
| Onboarding / first run | Level 7 (doctor) |
