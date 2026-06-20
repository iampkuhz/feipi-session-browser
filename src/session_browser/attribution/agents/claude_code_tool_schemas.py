"""Claude Code tool schema extraction 和 token pre-computation.

Claude Code–specific module: extracts tool definitions from the Claude Code
npm package (`sdk-tools.d.ts`), merges them with actual runtime descriptions
extracted from the Claude Code binary, and pre-computes per-tool token counts.

File-level isolation: this module is ONLY for Claude Code.  Qoder, Codex, and
other agents should have their own equivalent modules (e.g.
`agents/qoder_tool_schemas.py`) so that extraction logic, binary offsets, and
tool registries do not collide.

Usage:
    Full scan:  extract_tool_schemas(force=True)  # re-scans npm package
    Incremental: extract_tool_schemas()            # uses cached result
    Token count: get_tool_schema_tokens("Bash")
    All tokens:  get_all_tool_schema_tokens(["Bash", "Read", "Edit"])
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Cache file，用于 extracted tool schemas (Claude Code only).
_SCHEMA_CACHE_PATH = Path(__file__).parent / ".tool_schemas_cache.json"

# 兜底 to npm package，如果 local extraction fails.
_NPM_PACKAGE_PATHS = [
    Path("/tmp/claude-code-tools/package/sdk-tools.d.ts"),
]


# ---------------------------------------------------------------------------
# Full runtime descriptions extracted，来源于 该 Claude Code binary.
# ---------------------------------------------------------------------------
# These are 该 ACTUAL descriptions sent to 该 Anthropic API, assembled at
# runtime via Zod .describe() 和 template functions (uqK, $N9, etc.).
# Significantly longer than TypeScript JSDoc，用于 tools like Bash 和 Read.
#
# 说明：Extraction notes:
# 说明：Bash   – binary offset 197089397 (uqK function, normal mode, tJ()=false).
# 说明：Assembled from: base + working_dir + avoid + np(q) + transition
# 说明：+ # Instructions (np(A) + T + $) + bqK() + xqK() sandbox +
# 说明：IqK() git/PR instructions.  Total ~12 K chars.
# 读取   – binary offset ~197M ($N9 function).  ~1.4 K chars.
# 说明：Grep   – binary offset ~197M + TypeScript.  ~0.5 K chars.
# 说明：Edit   – binary + TypeScript.  ~0.3 K chars.
# 写入  – binary + TypeScript.  ~0.3 K chars.
# 说明：Glob   – binary + TypeScript.  ~0.2 K chars.
# Others –，来源于 binary strings 或 TypeScript JSDoc (short descriptions).
# ---------------------------------------------------------------------------
_BINARY_TOOL_DESCRIPTIONS: dict[str, str] = {
    "Bash": (
        "Executes a given bash command and returns its output.\n\n"
        "The working directory persists between commands, but shell state does not. "
        "The shell environment is initialized from the user's profile (bash or zsh).\n\n"
        "IMPORTANT: Avoid using this tool to run `find`, `grep`, `cat`, `head`, `tail`, "
        "`sed`, `awk`, or `echo` commands, unless explicitly instructed or after you have "
        "verified that a dedicated tool cannot accomplish your task. Instead, use the "
        "appropriate dedicated tool as this will provide a much better experience for the user:\n\n"
        "- File search: Use Glob (NOT find or ls)\n"
        "- Content search: Use Grep (NOT grep or rg)\n"
        "- Read files: Use Read (NOT cat/head/tail)\n"
        "- Edit files: Use Edit (NOT sed/awk)\n"
        "- Write files: Use Write (NOT echo >/cat <<EOF)\n"
        "- Communication: Output text directly (NOT echo/printf)\n\n"
        "While the Bash tool can do similar things, it's better to use the built-in tools "
        "as they provide a better user experience and make it easier to review tool calls "
        "and give permission.\n\n"
        "# Instructions\n\n"
        "- When issuing multiple commands:\n"
        "  - If the commands are independent and can run in parallel, make multiple Bash "
        "tool calls in a single message. Example: if you need to run \"git status\" and "
        "\"git diff\", send a single message with two Bash tool calls in parallel.\n"
        "  - If the commands depend on each other and must run sequentially, use a single "
        "Bash call with '&&' to chain them together.\n"
        "- Use ';' only when you need to run commands sequentially but don't care if earlier "
        "commands fail.\n"
        "- DO NOT use newlines to separate commands (newlines are ok in quoted strings).\n\n"
        "For git commands:\n"
        "- Prefer to create a new commit rather than amending an existing commit.\n"
        "- Before running destructive operations (e.g., git reset --hard, git push --force, "
        "git checkout --), consider whether there is a safer alternative that achieves the "
        "same goal. Only use destructive operations when they are truly the best approach.\n"
        "- Never skip hooks (--no-verify) or bypass signing (--no-gpg-sign, "
        "-c commit.gpgsign=false) unless the user has explicitly asked for it. If a hook "
        "fails, investigate and fix the underlying issue.\n\n"
        "Avoid unnecessary `sleep` commands:\n"
        "- Do not sleep between commands that can run immediately — just run them.\n"
        "- If your command is long running and you would like to be notified when it finishes "
        "— use `run_in_background`. No sleep needed.\n"
        "- Do not retry failing commands in a sleep loop — diagnose the root cause.\n"
        "- If waiting for a background task you started with `run_in_background`, you will be "
        "notified when it completes — do not poll.\n\n"
        "- If your command will create new directories or files, first use this tool to run "
        "`ls` to verify the parent directory exists and is the correct location.\n"
        "- Always quote file paths that contain spaces with double quotes in your command "
        "(e.g., cd \"path with spaces/file.txt\")\n"
        "- Try to maintain your current working directory throughout the session by using "
        "absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly "
        "requests it. In particular, never prepend `cd <current-directory>` to a `git` "
        "command — `git` already operates on the current working tree, and the compound "
        "triggers a permission prompt.\n"
        "- You may specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). "
        "By default, your command will timeout after 120000ms (2 minutes).\n\n"
        "- You can use the `run_in_background` parameter to run the command in the background. "
        "Only use this if you don't need the result immediately and are OK being notified "
        "when the command completes later. You do not need to check the output right away - "
        "you'll be notified when it finishes. You do not need to use '&' at the end of the "
        "command when using this parameter.\n\n"
        "## Command sandbox\n"
        "By default, your command will be run in a sandbox. This sandbox controls which "
        "directories and network hosts commands may access or modify without an explicit "
        "override.\n\n"
        "The sandbox has the following restrictions:\n"
        "Filesystem: (determined by sandbox config)\n"
        "Network: (determined by sandbox config)\n\n"
        "If a command fails due to sandbox restrictions, you can retry with "
        "`dangerouslyDisableSandbox: true`. This will prompt the user for permission.\n\n"
        "You should always default to running commands within the sandbox. Do NOT attempt "
        "to set `dangerouslyDisableSandbox: true` unless:\n"
        "- The user *explicitly* asks you to bypass sandbox\n"
        "- A specific command just failed and you see evidence of sandbox restrictions "
        "causing the failure. Note that commands can fail for many reasons unrelated to the "
        "sandbox (missing files, wrong arguments, network issues, etc.).\n\n"
        "Evidence of sandbox-caused failures includes:\n"
        "- \"Operation not permitted\" errors for file/network operations\n"
        "- Access denied to specific paths outside allowed directories\n"
        "- Network connection failures to non-whitelisted hosts\n"
        "- Unix socket connection errors\n\n"
        "When you see evidence of sandbox-caused failure:\n"
        "- Immediately retry with `dangerouslyDisableSandbox: true` (don't ask, just do it)\n"
        "- Briefly explain what sandbox restriction likely caused the failure. Be sure to "
        "mention that the user can use the `/sandbox` command to manage restrictions.\n"
        "- This will prompt the user for permission\n\n"
        "Treat each command you execute with `dangerouslyDisableSandbox: true` individually. "
        "Even if you have recently run a command with this setting, you should default to "
        "running future commands within the sandbox.\n"
        "- Do not suggest adding sensitive paths like ~/.bashrc, ~/.zshrc, ~/.ssh/*, or "
        "credential files to the sandbox allowlist.\n\n"
        "For temporary files, always use the `$TMPDIR` environment variable. TMPDIR is "
        "automatically set to the correct sandbox-writable directory in sandbox mode. "
        "Do NOT use `/tmp` directly - use `$TMPDIR` instead.\n\n"
        "## Git\n"
        "- Interactive flags (`-i`, e.g. `git rebase -i`, `git add -i`) are not supported "
        "in this environment.\n"
        "- Use the `gh` CLI for GitHub operations (PRs, issues, API).\n"
        "- Commit or push only when the user asks. If on the default branch, branch first.\n\n"
        "# Committing changes with git\n\n"
        "Only create commits when requested by the user. If unclear, ask first. When the "
        "user asks you to create a new git commit, follow these steps carefully:\n\n"
        "You can call multiple tools in a single response. When multiple independent pieces "
        "of information are requested and all commands are likely to succeed, run multiple "
        "tool calls in parallel for optimal performance. The numbered steps below indicate "
        "which commands should be batched in parallel.\n\n"
        "Git Safety Protocol:\n"
        "- NEVER update the git config\n"
        "- NEVER run destructive git commands (push --force, reset --hard, checkout ., "
        "restore ., clean -f, branch -D) unless the user explicitly requests these actions. "
        "Taking unauthorized destructive actions is unhelpful and can result in lost work, "
        "so it's best to ONLY run these commands when given direct instructions\n"
        "- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly "
        "requests it\n"
        "- NEVER run force push to main/master, warn the user if they request it\n"
        "- CRITICAL: Always create NEW commits rather than amending, unless the user "
        "explicitly requests a git amend. When a pre-commit hook fails, the commit did NOT "
        "happen — so --amend would modify the PREVIOUS commit, which may result in "
        "destroying work or losing previous changes. Instead, after hook failure, fix the "
        "issue, re-stage, and create a NEW commit\n"
        "- When staging files, prefer adding specific files by name rather than using "
        "\"git add -A\" or \"git add .\", which can accidentally include sensitive files "
        "(.env, credentials) or large binaries\n"
        "- NEVER commit changes unless the user explicitly asks you to. It is VERY IMPORTANT "
        "to only commit when explicitly asked, otherwise the user will feel that you are "
        "being too proactive\n\n"
        "1. Run the following bash commands in parallel, each using the Bash tool:\n"
        "  - Run a git status command to see all untracked files. IMPORTANT: Never use the "
        "-uall flag as it can cause memory issues on large repos.\n"
        "  - Run a git diff command to see both staged and unstaged changes that will be "
        "committed.\n"
        "  - Run a git log command to see recent commit messages, so that you can follow "
        "this repository's commit message style.\n"
        "2. Analyze all staged changes (both previously staged and newly added) and draft "
        "a commit message:\n"
        "  - Summarize the nature of the changes (eg. new feature, enhancement to an "
        "existing feature, bug fix, refactoring, test, docs, etc.). Ensure the message "
        "accurately reflects the changes and their purpose (i.e. \"add\" means a wholly "
        "new feature, \"update\" means an enhancement to an existing feature, \"fix\" means "
        "a bug fix, etc.).\n"
        "  - Do not commit files that likely contain secrets (.env, credentials.json, etc). "
        "Warn the user if they specifically request to commit those files\n"
        "  - Draft a concise (1-2 sentences) commit message that focuses on the \"why\" "
        "rather than the \"what\"\n"
        "  - Ensure it accurately reflects the changes and their purpose\n"
        "3. Run the following commands in parallel:\n"
        "   - Add relevant untracked files to the staging area.\n"
        "   - Create the commit with a message.\n"
        "   - Run git status after the commit completes to verify success.\n"
        "   Note: git status depends on the commit completing, so run it sequentially after "
        "the commit.\n"
        "4. If the commit fails due to pre-commit hook: fix the issue and create a NEW "
        "commit\n\n"
        "Important notes:\n"
        "- NEVER run additional commands to read or explore code, besides git bash commands\n"
        "- DO NOT push to the remote repository unless the user explicitly asks you to do so\n"
        "- IMPORTANT: Never use Git commands with the -i flag (like git rebase -i or git "
        "add -i) since they require interactive input which is not supported.\n"
        "- IMPORTANT: Do not use --no-edit with git rebase commands, as the --no-edit flag "
        "is not a valid option for git rebase.\n"
        "- If there are no changes to commit (i.e., no untracked files and no modifications), "
        "do not create an empty commit\n"
        "- In order to ensure good formatting, ALWAYS pass the commit message via a HEREDOC, "
        "a la this example:\n"
        "<example>\n"
        "git commit -m \"$(cat <<'EOF'\n"
        "   Commit message here.\n"
        "   EOF\n"
        "   )\"\n"
        "</example>\n\n"
        "# Creating pull requests\n"
        "Use the gh command via the Bash tool for ALL GitHub-related tasks including working "
        "with issues, pull requests, checks, and releases. If given a Github URL use the "
        "gh command to get the information needed.\n\n"
        "IMPORTANT: When the user asks you to create a pull request, follow these steps "
        "carefully:\n\n"
        "1. Run the following bash commands in parallel using the Bash tool, in order to "
        "understand the current state of the branch since it diverged from the main branch:\n"
        "   - Run a git status command to see all untracked files (never use -uall flag)\n"
        "   - Run a git diff command to see both staged and unstaged changes that will be "
        "committed\n"
        "   - Check if the current branch tracks a remote branch and is up to date with "
        "the remote, so you know if you need to push to the remote\n"
        "   - Run a git log command and `git diff [base-branch]...HEAD` to understand the "
        "full commit history for the current branch (from the time it diverged from the "
        "base branch)\n"
        "2. Analyze all changes that will be included in the pull request, making sure to "
        "look at all relevant commits (NOT just the latest commit, but ALL commits that will "
        "be included in the pull request!!!), and draft a pull request title and summary:\n"
        "   - Keep the PR title short (under 70 characters)\n"
        "   - Use the description/body for details, not the title\n"
        "3. Run the following commands in parallel:\n"
        "   - Create new branch if needed\n"
        "   - Push to remote with -u flag if needed\n"
        "   - Create PR using gh pr create with the format below. Use a HEREDOC to pass the "
        "body to ensure correct formatting.\n"
        "<example>\n"
        "gh pr create --title \"the pr title\" --body \"$(cat <<'EOF'\n"
        "## Summary\n"
        "<1-3 bullet points>\n\n"
        "## Test plan\n"
        "[Bulleted markdown checklist of TODOs for testing the pull request...]\n\n"
        "\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n"
        "EOF\n"
        ")\"\n"
        "</example>\n\n"
        "Important:\n"
        "- DO NOT use the TaskCreate or Agent tools\n"
        "- Return the PR URL when you're done, so the user can see it\n\n"
        "# Other common operations\n"
        "- View comments on a Github PR: gh api repos/foo/bar/pulls/123/comments"
    ),
    "Read": (
        "Reads a file from the local filesystem. You can access any file directly by "
        "using this tool.\n"
        "Assume this tool is able to read all files on the machine. If the User provides "
        "a path to a file assume that path is valid. It is okay to read a file that does "
        "not exist; an error will be returned.\n\n"
        "Usage:\n"
        "- The file_path parameter must be an absolute path, not a relative path\n"
        "- By default, it reads up to 2000 lines starting from the beginning of the file\n"
        "- You can optionally specify a line offset and limit, but it's recommended to "
        "read the whole file\n"
        "- When you already know which part of the file you need, only read that part\n"
        "- This tool allows Claude Code to read images (eg PNG, JPG, etc). When reading "
        "an image file the contents are presented visually as Claude Code is a multimodal "
        "LLM.\n"
        "- This tool can read PDF files (.pdf). For large PDFs (more than 10 pages), "
        "you MUST provide the pages parameter. Maximum 20 pages per request.\n"
        "- This tool can read Jupyter notebooks (.ipynb files) and returns all cells "
        "with their outputs.\n"
        "- This tool can only read files, not directories.\n"
        "- You will regularly be asked to read screenshots. ALWAYS use this tool to view "
        "the file.\n"
        "- If you read a file that exists but has empty contents you will receive a "
        "system reminder warning.\n"
        "- Do NOT re-read a file you just edited to verify — Edit/Write would have "
        "errored if the change failed."
    ),
    "Grep": (
        "Searches for a regular expression pattern in files. Uses ripgrep (rg) as the "
        "underlying search engine. Recursively searches the current directory by default, "
        "respecting .gitignore files.\n\n"
        "Output modes:\n"
        "- \"content\": shows matching lines (supports -A/-B/-C context, -n line numbers)\n"
        "- \"files_with_matches\": shows file paths (default)\n"
        "- \"count\": shows match counts\n\n"
        "Defaults: output_mode=\"files_with_matches\", head_limit=250, -n=true. "
        "Pass head_limit=0 for unlimited."
    ),
    "Edit": (
        "Performs exact string replacements in files.\n\n"
        "Usage:\n"
        "- The file_path parameter must be an absolute path\n"
        "- The old_string must match the file content exactly (including whitespace)\n"
        "- The new_string must be different from old_string\n"
        "- Use replace_all to replace all occurrences of old_string"
    ),
    "Write": (
        "Writes a file to the local filesystem, overwriting if one exists.\n\n"
        "Usage:\n"
        "- The file_path parameter must be an absolute path, not relative\n"
        "- This tool will overwrite the existing file if there is one at the provided path\n"
        "- If this is an existing file, you MUST use the Read tool first\n"
        "- Prefer the Edit tool for partial changes"
    ),
    "Glob": (
        "Fast file pattern matching tool that works with any codebase size.\n\n"
        "Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\". "
        "Returns matching file paths sorted by modification time. "
        "Results limited to 100 files.\n\n"
        "- When you are doing an open ended search that may require multiple rounds of "
        "globbing and grepping, use the Agent tool instead"
    ),
    "Agent": (
        "Launch a new agent to handle complex, multi-step tasks. Each agent type has "
        "specific capabilities and tools available to it.\n\n"
        "Available agent types and the tools they have access to:\n"
        "- implementer: For executing a scoped implementation task. Only use when the main "
        "agent has clearly defined Goal, Task id, Allowed files/directories, Forbidden "
        "files/directories, Required context files, Expected output, Validation command, "
        "and Failure policy. Do not use for broad exploration, OpenSpec planning, "
        "QA-only verification, UI design analysis, repository mapping, or task slicing.\n\n"
        "## When not to use\n\n"
        "If the target is already known, use the direct tool: Read for a known path, "
        "`grep` via the Bash tool for a specific symbol or string. Reserve this tool for "
        "open-ended questions that span the codebase, or tasks that match an available agent type.\n\n"
        "## Usage notes\n\n"
        "- Always include a short description summarizing what the agent will do\n"
        "- When you launch multiple agents for independent work, send them in a single "
        "message with multiple tool use content blocks so they run concurrently\n"
        "- When the agent is done, it will return a single message back to you. The result "
        "returned by the agent is not visible to the user. To show the user the result, "
        "you should send a text message back to the user with a concise summary of the result.\n"
        "- Trust but verify: an agent's summary describes what it intended to do, not "
        "necessarily what it did. When an agent writes or edits code, check the actual "
        "changes before reporting the work as done.\n"
        "- You can optionally run agents in the background using the run_in_background "
        "parameter. When an agent runs in the background, you will be automatically "
        "notified when it completes — do NOT sleep, poll, or proactively check on its "
        "progress. Continue with other work or respond to the user instead.\n"
        "- **Foreground vs background**: Use foreground (default) when you need the agent's "
        "results before you can proceed — e.g., research agents whose findings inform your "
        "next steps. Use background when you have genuinely independent work to do in parallel.\n"
        "- To continue a previously spawned agent, use SendMessage with the agent's ID or "
        "name as the `to` field — that resumes it with full context. A new Agent call "
        "starts a fresh agent with no memory of prior runs, so the prompt must be self-contained.\n"
        "- Clearly tell the agent whether you expect it to write code or just to do research "
        "(search, file reads, web fetches, etc.), since it is not aware of the user's intent\n"
        "- If the agent description mentions that it should be used proactively, then you "
        "should try your best to use it without the user having to ask for it first.\n"
        "- If the user specifies that they want you to run agents \"in parallel\", you MUST "
        "send a single message with multiple Agent tool use content blocks.\n\n"
        "## Writing the prompt\n\n"
        "Brief the agent like a smart colleague who just walked into the room — it hasn't "
        "seen this conversation, doesn't know what you've tried, doesn't understand why this "
        "task matters.\n"
        "- Explain what you're trying to accomplish and why.\n"
        "- Describe what you've already learned or ruled out.\n"
        "- Give enough context about the surrounding problem that the agent can make "
        "judgment calls rather than just following a narrow instruction.\n"
        "- If you need a short response, say so (\"report in under 200 words\").\n"
        "- Lookups: hand over the exact command. Investigations: hand over the question — "
        "prescribed steps become dead weight when the premise is wrong.\n\n"
        "Terse command-style prompts produce shallow, generic work."
    ),
    "EnterPlanMode": (
        "Enters plan mode. Use this when the user's request is unclear or when you need "
        "to explore the codebase before proposing a solution. In plan mode, you can read "
        "files and run commands but cannot make edits. Exit plan mode when you have a "
        "clear plan and the user has approved it.\n\n"
        "## When to use\n\n"
        "- The user's request is ambiguous or has multiple valid interpretations\n"
        "- You need to understand the codebase structure before proposing changes\n"
        "- The task involves architectural decisions that need discussion\n"
        "- You're unsure about the user's intent and want to confirm before acting\n\n"
        "## When NOT to use\n\n"
        "- The task is clear and straightforward — just do it\n"
        "- You already know the file paths and changes needed\n"
        "- The user has explicitly asked you to implement something directly"
    ),
    "ExitPlanMode": (
        "Exits plan mode. Use this after you have explored the codebase and have a clear "
        "plan that the user has approved. This will allow you to start making edits."
    ),
    "TodoWrite": (
        "Use this tool to create and manage a structured task list for your current coding "
        "session. This helps you track progress, organize complex tasks, and demonstrate "
        "thoroughness to the user.\n\n"
        "## When to Use This Tool\n\n"
        "Use this tool proactively in these scenarios:\n\n"
        "- Complex multi-step tasks - When a task requires 3 or more distinct steps or actions\n"
        "- Non-trivial and complex tasks - Tasks that require careful planning or multiple "
        "operations\n"
        "- Plan mode - When using plan mode, create a task list to track the work\n"
        "- User explicitly requests todo list - When the user directly asks you to use the "
        "todo list\n"
        "- User provides multiple tasks - When users provide a list of things to be done "
        "(numbered or comma-separated)\n"
        "- After receiving new instructions - Immediately capture user requirements as tasks\n"
        "- When you start working on a task - Mark it as in_progress BEFORE beginning work\n"
        "- After completing a task - Mark it as completed and add any new follow-up tasks "
        "discovered during implementation\n\n"
        "## When NOT to Use This Tool\n\n"
        "Skip using this tool when:\n"
        "- There is only a single, straightforward task\n"
        "- The task is trivial and tracking it provides no organizational benefit\n"
        "- The task can be completed in less than 3 trivial steps\n"
        "- The task is purely conversational or informational\n\n"
        "## Tips\n\n"
        "- Create tasks with clear, specific subjects that describe the outcome\n"
        "- After creating tasks, use TaskUpdate to set up dependencies (blocks/blockedBy) if needed\n"
        "- Check TaskList first to avoid creating duplicate tasks"
    ),
    "WebFetch": (
        "- Fetches content from a specified URL and processes it using an AI model\n"
        "- Takes a URL and a prompt as input\n"
        "- Fetches the URL content, converts HTML to markdown\n"
        "- Processes the content with the prompt using a small, fast model\n"
        "- Returns the model's response about the content\n"
        "- Use this tool when you need to retrieve and analyze web content\n\n"
        "Usage notes:\n"
        "  - IMPORTANT: If an MCP-provided web fetch tool is available, prefer using "
        "that tool instead of this one, as it may have fewer restrictions.\n"
        "  - The URL must be a fully-formed valid URL\n"
        "  - HTTP URLs will be automatically upgraded to HTTPS\n"
        "  - The prompt should describe what information you want to extract from the page\n"
        "  - This tool is read-only and does not modify any files\n"
        "  - Results may be summarized if the content is very large\n"
        "  - Includes a self-cleaning 15-minute cache for faster responses when repeatedly "
        "accessing the same URL\n"
        "  - When a URL redirects to a different host, the tool will inform you and provide "
        "the redirect URL in a special format. You should then make a new WebFetch request "
        "with the redirect URL to fetch the content.\n"
        "  - For GitHub URLs, prefer using the gh CLI via Bash instead (e.g., gh pr view, "
        "gh issue view, gh api)."
    ),
    "WebSearch": (
        "- Returns search result information formatted as search result blocks, including "
        "links as markdown hyperlinks\n"
        "- Use this tool for accessing information beyond Claude's knowledge cutoff\n"
        "- Searches are performed automatically within a single API call\n\n"
        "CRITICAL REQUIREMENT - You MUST follow this:\n"
        "  - After answering the user's question, you MUST include a \"Sources:\" section "
        "at the end of your response\n"
        "  - In the Sources section, list all relevant URLs from the search results as "
        "markdown hyperlinks: [Title](URL)\n"
        "  - This is MANDATORY - never skip including sources in your response\n"
        "  - Example format:\n\n"
        "    [Your answer here]\n\n"
        "    Sources:\n"
        "    - [Source Title 1](https://example.com/1)\n"
        "    - [Source Title 2](https://example.com/2)\n\n"
        "Usage notes:\n"
        "  - Domain filtering is supported to include or block specific websites\n"
        "  - Web search is only available in the US\n\n"
        "IMPORTANT - Use the correct year in search queries:\n"
        "  - The current month is"
    ),
    "TaskCreate": (
        "Creates a new task. Tasks are tracked in the session and can be managed via the "
        "TaskUpdate, TaskGet, and TaskList tools.\n\n"
        "## Task Fields\n\n"
        "- **subject**: A brief, actionable title in imperative form (e.g., \"Fix authentication bug in login flow\")\n"
        "- **description**: What needs to be done\n"
        "- **activeForm** (optional): Present continuous form shown in the spinner when in_progress (e.g., \"Fixing authentication bug\")\n\n"
        "All tasks are created with status `pending`."
    ),
    "TaskUpdate": (
        "Updates an existing task. Can change status, subject, description, owner, and "
        "dependencies between tasks.\n\n"
        "## When to Use This Tool\n\n"
        "**Mark tasks as resolved:**\n"
        "- When you have completed the work described in a task\n"
        "- When a task is no longer needed or has been superseded\n"
        "- IMPORTANT: Always mark your assigned tasks as resolved when you finish them\n"
        "- After resolving, call TaskList to find your next task\n\n"
        "- ONLY mark a task as completed when you have FULLY accomplished it\n"
        "- If you encounter errors, blockers, or cannot finish, keep the task as in_progress\n"
        "- When blocked, create a new task describing what needs to be resolved\n"
        "- Never mark a task as completed if:\n"
        "  - Tests are failing\n"
        "  - Implementation is partial\n"
        "  - You encountered unresolved errors\n"
        "  - You couldn't find necessary files or dependencies\n\n"
        "**Delete tasks:**\n"
        "- When a task is no longer relevant or was created in error\n"
        "- Setting status to `deleted` permanently removes the task\n\n"
        "**Update task details:**\n"
        "- When requirements change or become clearer\n"
        "- When establishing dependencies between tasks\n\n"
        "## Status Workflow\n\n"
        "Status progresses: `pending` → `in_progress` → `completed`\n\n"
        "Use `deleted` to permanently remove a task."
    ),
    "TaskList": (
        "Lists all tasks. Returns a summary of each task.\n\n"
        "## When to Use This Tool\n\n"
        "- To see what tasks are available to work on (status: 'pending', no owner, not blocked)\n"
        "- To check overall progress on the project\n"
        "- To find tasks that are blocked and need dependencies resolved\n"
        "- After completing a task, to check for newly unblocked work or claim the next available task\n"
        "- **Prefer working on tasks in ID order** (lowest ID first) when multiple tasks are "
        "available, as earlier tasks often set up context for later ones"
    ),
    "TaskGet": (
        "Gets task details by task ID. Returns the task's subject, description, status, "
        "and any metadata.\n\n"
        "## When to Use This Tool\n\n"
        "- When you need the full description and context before starting work on a task\n"
        "- To understand task dependencies (what it blocks, what blocks it)\n"
        "- After being assigned a task, to get complete requirements\n\n"
        "## Tips\n\n"
        "- After fetching a task, verify its blockedBy list is empty before beginning work.\n"
        "- Use TaskList to see all tasks in summary form."
    ),
    "TaskStop": (
        "- Stops a running background task by its ID\n"
        "- Takes a task_id parameter identifying the task to stop\n"
        "- Returns a success or failure status\n"
        "- Use this tool when you need to terminate a long-running task"
    ),
    "TaskOutput": (
        "Gets output from a background task. Waits for new output if the task is still "
        "running.\n\n"
        "Use this to monitor the progress of a background agent or retrieve its results. "
        "If the task has completed, returns all accumulated output immediately."
    ),
    "NotebookEdit": (
        "Edits a Jupyter notebook (.ipynb) cell. Replaces the source of a specific cell "
        "or inserts a new cell.\n\n"
        "Usage:\n"
        "- Specify the cell index or cell ID to edit\n"
        "- Provide the new source code for the cell\n"
        "- Can insert a new cell at a specific position"
    ),
    "REPL": (
        "Executes JavaScript code in a Read-Eval-Print Loop (REPL) environment. Useful "
        "for testing JavaScript snippets.\n\n"
        "The REPL maintains state between calls, so variables and functions defined in "
        "previous calls are available in subsequent calls."
    ),
    "Workflow": (
        "Runs a workflow script. Executes a predefined sequence of actions.\n\n"
        "Used to run automated workflows within the Claude Code environment."
    ),
    "AskUserQuestion": (
        "Asks the user multiple choice questions to gather information, clarify ambiguity, "
        "understand preferences, make decisions or offer them choices."
    ),
    "CronCreate": (
        "Creates a scheduled cron job that runs a command at specified intervals.\n\n"
        "Usage:\n"
        "- Provide a cron schedule string (e.g., \"0 9 * * *\" for 9 AM daily)\n"
        "- Provide the command to run\n"
        "- Optionally set a description for the job"
    ),
    "CronDelete": (
        "Deletes a scheduled cron job.\n\n"
        "Provide the cron job ID to delete. The job will be permanently removed from the schedule."
    ),
    "CronList": (
        "Lists all scheduled cron jobs.\n\n"
        "Returns the ID, schedule, command, and description for each active cron job."
    ),
    "ScheduleWakeup": (
        "Schedule when to resume work in /loop dynamic mode (always pass the `prompt` arg). "
        "Call before ending the turn to keep the loop alive; omit the call to end it."
    ),
    "RemoteTrigger": (
        "Triggers a remote action on a connected service.\n\n"
        "Used to invoke external service endpoints or webhook actions configured in "
        "the Claude Code environment."
    ),
    "Monitor": (
        "Monitors a command's output in real time. Useful for long-running processes.\n\n"
        "Each stdout line is a notification. For one-shot \"wait until done,\" use Bash "
        "with run_in_background instead."
    ),
    "PushNotification": (
        "Send a notification to the user via their terminal and, when Remote Control is "
        "connected, also push to their mobile device"
    ),
    "EnterWorktree": (
        "Enters a git worktree. Creates a separate working directory for a branch.\n\n"
        "Useful for working on a different branch without stashing or committing current work."
    ),
    "ExitWorktree": (
        "Exits a git worktree. Cleans up the temporary worktree directory."
    ),
    "ListMcpResources": (
        "Lists available MCP (Model Context Protocol) server resources.\n\n"
        "MCP servers provide tools and resources that extend Claude Code's capabilities."
    ),
    "ReadMcpResource": (
        "Reads a specific resource from an MCP server.\n"
        "- server: The name of the MCP server to read from\n"
        "- uri: The URI of the resource to read\n\n"
        "Usage examples:\n"
        "- Read a resource from a server: `readMcpResource({ server: \"myserver\", "
        "uri: \"my-resource-uri\" })`"
    ),
    "Mcp": (
        "Generic MCP (Model Context Protocol) tool invocation.\n\n"
        "Invoke a tool provided by a connected MCP server. Specify the server name, "
        "tool name, and arguments."
    ),
}

# 确保 every tool has 一个 description.
ALL_CLAUDE_CODE_TOOLS = [
    "Agent", "AskUserQuestion", "Bash", "CronCreate", "CronDelete", "CronList",
    "Edit", "EnterPlanMode", "EnterWorktree", "ExitPlanMode", "ExitWorktree",
    "Glob", "Grep", "ListMcpResources", "Mcp", "Monitor", "NotebookEdit",
    "PushNotification", "REPL", "Read", "ReadMcpResource", "RemoteTrigger",
    "ScheduleWakeup", "TaskCreate", "TaskGet", "TaskList", "TaskOutput",
    "TaskStop", "TaskUpdate", "TodoWrite", "WebFetch", "WebSearch", "Workflow",
    "Write",
]

for _tool in ALL_CLAUDE_CODE_TOOLS:
    _BINARY_TOOL_DESCRIPTIONS.setdefault(
        _tool, f"Tool: {_tool}. See Claude Code documentation for details."
    )


# 说明：Tool name mapping: TypeScript interface name -> actual tool name.
_TOOL_NAME_MAP: dict[str, str] = {
    "BashInput": "Bash",
    "FileReadInput": "Read",
    "FileWriteInput": "Write",
    "FileEditInput": "Edit",
    "GlobInput": "Glob",
    "GrepInput": "Grep",
    "AgentInput": "Agent",
    "TodoWriteInput": "TodoWrite",
    "WebFetchInput": "WebFetch",
    "WebSearchInput": "WebSearch",
    "TaskCreateInput": "TaskCreate",
    "TaskUpdateInput": "TaskUpdate",
    "TaskGetInput": "TaskGet",
    "TaskListInput": "TaskList",
    "TaskStopInput": "TaskStop",
    "TaskOutputInput": "TaskOutput",
    "NotebookEditInput": "NotebookEdit",
    "REPLInput": "REPL",
    "WorkflowInput": "Workflow",
    "AskUserQuestionInput": "AskUserQuestion",
    "EnterPlanModeInput": "EnterPlanMode",
    "ExitPlanModeInput": "ExitPlanMode",
    "CronCreateInput": "CronCreate",
    "CronDeleteInput": "CronDelete",
    "CronListInput": "CronList",
    "ScheduleWakeupInput": "ScheduleWakeup",
    "RemoteTriggerInput": "RemoteTrigger",
    "MonitorInput": "Monitor",
    "PushNotificationInput": "PushNotification",
    "EnterWorktreeInput": "EnterWorktree",
    "ExitWorktreeInput": "ExitWorktree",
    "ListMcpResourcesInput": "ListMcpResources",
    "ReadMcpResourceInput": "ReadMcpResource",
    "McpInput": "Mcp",
}


def _find_sdk_tools_file() -> Path | None:
    """Locate 该 sdk-tools.d.ts file，来源于 Claude Code npm package."""
    for p in _NPM_PACKAGE_PATHS:
        if p.exists():
            return p

    ext_dirs = Path.home().glob(
        ".vscode/extensions/anthropic.claude-code-*/package/sdk-tools.d.ts"
    )
    for p in ext_dirs:
        if p.exists():
            return p

    try:
        result = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            npm_root = Path(result.stdout.strip())
            candidate = (
                npm_root / "@anthropic-ai" / "claude-code" / "package" / "sdk-tools.d.ts"
            )
            if candidate.exists():
                return candidate
    except (OSError, subprocess.TimeoutExpired):
        pass

    return None


def _parse_ts_interface(
    content: str,
) -> dict[str, dict[str, Any]]:
    """解析 TypeScript interface blocks，来源于 sdk-tools.d.ts.

    Returns dict of {interface_name: {property_name: {type, description, required}}}.
    """
    result: dict[str, dict[str, Any]] = {}

    # Match export interface blocks, handling nested braces，用于 type literals.
    interface_pattern = r'export interface (\w+Input) \{((?:[^{}]|\{[^{}]*\})*)\}'

    for match in re.finditer(interface_pattern, content, re.DOTALL):
        name = match.group(1)
        body = match.group(2)
        props: dict[str, Any] = {}

        # Match JSDoc blocks of 该 form:
        #   /**
        # 说明：* Description text (may span multiple lines)
        #    */
        # 说明：propertyName?: Type;
        #
        # The description is captured non-greedily up to 该 closing */,
        # avoiding bleed，转换为 subsequent JSDoc blocks 或 TS code.
        prop_pattern = (
            r'/\*\*\s*\n'           # 匹配 opening /**
            r'(?:\s*\*[^\n]*\n)*?'  # 匹配零行或多行中间的 * 行
            r'\s*\*\s+'             # 匹配最后一个后接空白的 *
            r'((?:(?!\*/).)*?)'     # description：捕获直到 */ 前的内容
            r'\s*\*/'               # 匹配 closing */
            r'\s*\n\s*'             # 匹配空白或换行
            r'("?\??-?[\w.-]+"?)'   # property name：可带引号或包含 -
            r'(\?)?:\s*'            # optional marker：可选标记
            r'([^;]+);'             # type：捕获到 ; 为止
        )
        for jsdoc, prop_name, optional, prop_type in re.findall(prop_pattern, body):
            desc = re.sub(r'\n\s*\*\s*', ' ', jsdoc).strip()
            # Clean up property name: strip surrounding quotes，如果 present
            prop_name = prop_name.strip('"')
            props[prop_name] = {
                "description": desc[:300],
                "type": _map_ts_type(prop_type.strip()),
                "required": not bool(optional),
            }

        result[name] = props

    return result


def _map_ts_type(ts_type: str) -> str:
    """映射 TypeScript type to JSON Schema type string."""
    ts_type = ts_type.strip()
    if ts_type == "string":
        return "string"
    if ts_type == "number":
        return "number"
    if ts_type == "boolean":
        return "boolean"
    if "|" in ts_type:
        return "string"
    if ts_type.startswith('"') and ts_type.endswith('"'):
        return "string"
    if ts_type.endswith("[]"):
        return "array"
    return "string"


def _build_json_schema(
    tool_name: str,
    description: str,
    properties: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """构建 一个 JSON Schema tool definition matching 该 Anthropic API format."""
    props: dict[str, Any] = {}
    required: list[str] = []

    for prop_name, prop_info in properties.items():
        schema_prop: dict[str, Any] = {
            "type": prop_info["type"],
        }
        if prop_info.get("description"):
            schema_prop["description"] = prop_info["description"]
        props[prop_name] = schema_prop

        if prop_info.get("required", True):
            required.append(prop_name)

    return {
        "name": tool_name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": props,
            "required": required,
        },
    }


def extract_tool_schemas(
    *,
    force: bool = False,
) -> dict[str, dict[str, Any]]:
    """提取 tool schemas，来源于 Claude Code npm package.

    Merges TypeScript interface properties with actual runtime descriptions
    extracted from the Claude Code binary.

    Args:
        force: If True, re-scans the npm package even if cached.

    Returns:
        Dict of {tool_name: json_schema_dict}.
    """
    if not force and _SCHEMA_CACHE_PATH.exists():
        try:
            cached = json.loads(_SCHEMA_CACHE_PATH.read_text(encoding="utf-8"))
            if cached:
                logger.debug("Loaded tool schemas from cache (%d tools)", len(cached))
                return cached
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("Cache read failed: %s", exc)

    sdk_path = _find_sdk_tools_file()
    if sdk_path is None:
        logger.warning("Cannot find sdk-tools.d.ts; using fallback heuristic schemas")
        return _build_fallback_schemas()

    try:
        content = sdk_path.read_text(encoding="utf-8")
        ts_interfaces = _parse_ts_interface(content)

        schemas: dict[str, dict[str, Any]] = {}
        for ts_name, properties in ts_interfaces.items():
            tool_name = _TOOL_NAME_MAP.get(ts_name, ts_name.replace("Input", ""))
            # 使用 binary description，如果 available, otherwise TypeScript JSDoc.
            description = _BINARY_TOOL_DESCRIPTIONS.get(tool_name, f"Tool: {tool_name}")
            schema = _build_json_schema(tool_name, description, properties)
            schemas[tool_name] = schema

        # 确保 ALL tools are present in 该 schema (fill gaps，用于 tools whose
        # 说明：TypeScript interfaces were not found in sdk-tools.d.ts).
        for tool_name in ALL_CLAUDE_CODE_TOOLS:
            if tool_name not in schemas:
                schemas[tool_name] = {
                    "name": tool_name,
                    "description": _BINARY_TOOL_DESCRIPTIONS.get(
                        tool_name, f"Tool: {tool_name}"
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                }

        _SCHEMA_CACHE_PATH.write_text(
            json.dumps(schemas, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Extracted %d tool schemas from %s", len(schemas), sdk_path)
        return schemas

    except (OSError, ValueError) as exc:
        logger.warning("Failed to extract tool schemas: %s; using fallback", exc)
        return _build_fallback_schemas()


def _build_fallback_schemas() -> dict[str, dict[str, Any]]:
    """构建 fallback tool schemas，当 npm package is unavailable."""
    schemas: dict[str, dict[str, Any]] = {}
    for tool_name, description in _BINARY_TOOL_DESCRIPTIONS.items():
        schemas[tool_name] = {
            "name": tool_name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
    return schemas


# ---------------------------------------------------------------------------
# token 估算辅助函数
# ---------------------------------------------------------------------------

def get_tool_schema_text(tool_name: str, schemas: dict[str, dict] | None = None) -> str:
    """Get 该 serialized JSON text，用于 一个 tool's schema.

    Returns the actual JSON representation that approximates what gets sent to
    the API, suitable for accurate token counting.
    """
    if schemas is None:
        schemas = extract_tool_schemas()

    schema = schemas.get(tool_name)
    if schema is None:
        return ""

    return json.dumps(schema, ensure_ascii=False)


def get_tool_schema_tokens(
    tool_name: str,
    schemas: dict[str, dict] | None = None,
    model: str = "",
) -> int:
    """Estimate token count，用于 一个 single tool's JSON schema.

    Uses the actual serialized JSON text for accurate counting.
    """
    from session_browser.attribution.token_estimator import estimate_tokens_from_text

    schema_text = get_tool_schema_text(tool_name, schemas)
    if not schema_text:
        return 0

    return estimate_tokens_from_text(schema_text, model)


def get_all_tool_schema_tokens(
    tool_names: list[str],
    schemas: dict[str, dict] | None = None,
    model: str = "",
) -> int:
    """Estimate total token count，用于 multiple tool schemas."""
    return sum(
        get_tool_schema_tokens(name, schemas, model)
        for name in tool_names
    )


# ---------------------------------------------------------------------------
# 模块级缓存
# ---------------------------------------------------------------------------

_extracted_schemas: dict[str, dict] | None = None


def get_cached_schemas() -> dict[str, dict]:
    """Get cached tool schemas, extracting，如果 necessary."""
    global _extracted_schemas
    if _extracted_schemas is None:
        _extracted_schemas = extract_tool_schemas()
    return _extracted_schemas


def invalidate_schema_cache() -> None:
    """Invalidate 该 module-level schema cache."""
    global _extracted_schemas
    _extracted_schemas = None
