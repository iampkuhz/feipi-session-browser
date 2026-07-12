from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_QODER_FILES = [
    ".qoder/README.md",
    ".qoder/AGENTS.md",
    ".qoder/settings.json",
    ".qoder/settings.local.example.json",
    ".qoder/agents/qoder-main-default.md",
    ".qoder/agents/runtime-isolation-diagnoser.md",
    ".qoder/agents/quality-gate-diagnoser.md",
    ".qoder/agents/java-backend-implementer.md",
    ".qoder/agents/session-ingestion-specialist.md",
    ".qoder/agents/ui-implementation-specialist.md",
    ".qoder/agents/mhtml-export-specialist.md",
    ".qoder/agents/privacy-reviewer.md",
]

SPECIALIST_SKILLS = {
    "quality-gate-diagnoser": "skills/authoring/feipi-quality-gate-diagnosis/SKILL.md",
    "java-backend-implementer": "skills/authoring/feipi-java-feature-dev/SKILL.md",
    "session-ingestion-specialist": "skills/authoring/feipi-session-ingestion-dev/SKILL.md",
    "ui-implementation-specialist": "skills/authoring/feipi-session-detail-ui-dev/SKILL.md",
    "mhtml-export-specialist": "skills/authoring/feipi-mhtml-export-dev/SKILL.md",
    "privacy-reviewer": "skills/authoring/feipi-privacy-redaction-dev/SKILL.md",
}


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_qoder_required_files_exist():
    missing = [path for path in REQUIRED_QODER_FILES if not (ROOT / path).is_file()]
    assert missing == []


def test_qoder_manifest_has_config_agents_and_skills():
    manifest = _read("harness/agent-runtime.manifest.yaml")
    qoder_start = manifest.index("  qoder:")
    qoder_end = manifest.index("shared_skills:", qoder_start)
    qoder_block = manifest[qoder_start:qoder_end]

    assert "- .qoder/AGENTS.md" in qoder_block
    assert "- .qoder/settings.json" in qoder_block
    assert "- .qoder/settings.local.example.json" in qoder_block
    assert "agents_dir: .qoder/agents" in qoder_block
    assert "skills_dir: .qoder/skills" in qoder_block
    for hook in [
        ".qoder/hooks/session-start.sh",
        ".qoder/hooks/cwd-changed.sh",
        ".qoder/hooks/user-prompt-submit.sh",
        ".qoder/hooks/pre_tool_bootstrap.sh",
        ".qoder/hooks/pre_tool_guard.sh",
        ".qoder/hooks/pre_write_guard.sh",
        ".qoder/hooks/post_bash_guard.sh",
        ".qoder/hooks/post_tool_guard.sh",
        ".qoder/hooks/stop_check.sh",
    ]:
        assert hook in qoder_block
        assert (ROOT / hook).is_file()


def test_qoder_agents_reference_shared_skills():
    for agent_name, skill_path in SPECIALIST_SKILLS.items():
        content = _read(f".qoder/agents/{agent_name}.md")
        assert skill_path in content

    runtime_content = _read(".qoder/agents/runtime-isolation-diagnoser.md")
    assert "EXPECTED_OUTCOMES.md" in runtime_content
    assert "scripts/agent_runtime/paths.py" in runtime_content


def test_check_qoder_runtime_parity_passes():
    result = subprocess.run(
        [sys.executable, "scripts/checks/check_qoder_runtime_parity.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "skipped_count=0" in result.stdout
