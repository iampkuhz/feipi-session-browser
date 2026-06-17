import pytest
from scripts.claude_hooks.classify import classify_file, required_quality_targets


@pytest.mark.contract_case("HOOK-HARNESS-002")
@pytest.mark.contract_case("HOOK-HARNESS-015")
def test_ui_classification():
    c = classify_file("src/session_browser/web/templates/detail.html")
    assert c.category == "ui-template"
    assert c.requires_quality_gate
    assert c.quality_target == "session-detail"


@pytest.mark.contract_case("HOOK-HARNESS-002")
def test_python_classification():
    c = classify_file("src/session_browser/core.py")
    assert c.category == "python-src"
    assert c.quality_target == "python-src"


@pytest.mark.contract_case("HOOK-HARNESS-002")
def test_hook_classification():
    c = classify_file(".claude/hooks/claude-hook.sh")
    assert c.category == "hook"
    assert c.quality_target == "hook-runtime"


@pytest.mark.contract_case("HOOK-HARNESS-002")
def test_cross_agent_hook_classification():
    assert classify_file(".codex/hooks/stop_check.sh").quality_target == "hook-runtime"
    assert classify_file(".qoder/hooks/stop_check.sh").quality_target == "hook-runtime"
    assert classify_file(".codex/hooks.json").quality_target == "hook-runtime"
    assert classify_file(".codex/config.toml").quality_target == "hook-runtime"
    assert classify_file("skills/authoring/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file(".agents/skills/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file(".codex/skills/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file(".claude/skills/feipi-openspec-orchestrate-change/SKILL.md").quality_target == "hook-runtime"
    assert classify_file("AGENTS.md").quality_target == "hook-runtime"
    assert classify_file("CLAUDE.md").quality_target == "hook-runtime"


@pytest.mark.contract_case("HOOK-HARNESS-002")
def test_acceptance_contract_classification():
    doc = classify_file("docs/acceptance-contracts/features/DATA_PRESENTERS.md")
    test = classify_file("tests/backend/test_round_signals.py")
    assert doc.category == "acceptance-contract"
    assert doc.requires_quality_gate
    assert doc.quality_target == "acceptance-contracts"
    assert test.category == "test"
    assert test.requires_quality_gate
    assert test.quality_target == "acceptance-contracts"


@pytest.mark.contract_case("HOOK-HARNESS-002")
def test_targets_deduped():
    assert required_quality_targets(["src/session_browser/a.py", "src/session_browser/b.py"]) == ["python-src"]


@pytest.mark.contract_case("HOOK-HARNESS-002")
def test_acceptance_contract_target_required():
    targets = required_quality_targets([
        "docs/acceptance-contracts/features/DATA_PRESENTERS.md",
        "tests/backend/test_round_signals.py",
    ])
    assert targets == ["acceptance-contracts"]
