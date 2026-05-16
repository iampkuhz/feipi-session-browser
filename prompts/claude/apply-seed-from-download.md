# Apply seed v2 from Downloads into current repository

You are running Claude Code from the real target repository:

```text
/Users/zhehan/Documents/tools/llm/feipi-session-browser
```

The seed package has been unzipped at:

```text
~/Downloads/feipi_session_browser_harness_seed2
```

Your task is to migrate the harness from the seed package into the current repository in a controlled, high-quality way.

## Absolute constraints

1. Do not delete existing product code.
2. Do not blindly copy the entire seed over the current repository.
3. Do not start implementation changes before creating an OpenSpec change.
4. Do not leave placeholders, stubs, or unfinished markers.
5. Do not modify user-local files such as `.claude/settings.local.json` if it exists.
6. Preserve `.git/` and current repository history.
7. Work serially. Use subagents for bounded inspection/review tasks, not for uncontrolled parallel edits.

## Required workflow

### Phase 0: Inspect both trees

Inspect:

```bash
pwd
find . -maxdepth 3 -type f | sort | sed 's#^./##' | head -200
find ~/Downloads/feipi_session_browser_harness_seed2 -maxdepth 4 -type f | sort | head -300
```

Read:

```text
~/Downloads/feipi_session_browser_harness_seed2/MANIFEST.md
~/Downloads/feipi_session_browser_harness_seed2/seed-overlay/CLAUDE.md
~/Downloads/feipi_session_browser_harness_seed2/seed-overlay/harness/README.md
~/Downloads/feipi_session_browser_harness_seed2/seed-overlay/openspec/README.md
```

### Phase 1: Create OpenSpec change first

Create a new OpenSpec change in the current repository:

```text
openspec/changes/install-agent-harness-v2/
  proposal.md
  design.md
  tasks.md
  specs/agent-harness/spec.md
  specs/openspec-workflow/spec.md
  specs/claude-code-harness/spec.md
```

Base it on the seed's bootstrap change but adapt it to the current repository after inspection.

### Phase 2: Install or merge harness files

Merge the seed overlay into the current repository:

```text
~/Downloads/feipi_session_browser_harness_seed2/seed-overlay/
```

Rules:

- If a target file does not exist, copy it.
- If a target file exists, inspect both versions and merge carefully.
- If current repo has a more accurate implementation-specific note, preserve it.
- Keep `CLAUDE.md` and `AGENTS.md` slim. Put detailed instructions under `harness/` and `docs/`.
- Ensure `.claude/settings.local.json` is not created or overwritten; only provide `.claude/settings.local.example.json`.

### Phase 3: Validate

Run validation commands if available, otherwise create the scripts first from seed:

```bash
python3 scripts/harness/validate_harness_structure.py
python3 scripts/harness/check_no_unfinished_markers.py
python3 scripts/harness/validate_openspec_layout.py
python3 scripts/harness/validate_task_files.py
```

Then inspect git diff:

```bash
git status --short
git diff --stat
git diff -- . ':(exclude)vendor' ':(exclude).git'
```

### Phase 4: Report

Return a concise report:

- Files added.
- Files merged.
- Existing files preserved.
- OpenSpec change created.
- Validation commands and results.
- Remaining work as explicit OpenSpec changes, not casual notes.

## Quality bar

The result should make future work follow this loop:

```text
OpenSpec change -> task files -> single-threaded Claude Code execution -> validation -> archive
```

Do not convert the current repository into an over-broad prompt dump. The harness must be structured, progressive-loaded, and maintainable.
