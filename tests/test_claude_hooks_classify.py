from scripts.claude_hooks.classify import classify_file, required_quality_targets


def test_ui_classification():
    c = classify_file("src/session_browser/web/templates/detail.html")
    assert c.category == "ui-template"
    assert c.requires_quality_gate
    assert c.quality_target == "session-detail"


def test_python_classification():
    c = classify_file("src/session_browser/core.py")
    assert c.category == "python-src"
    assert c.quality_target == "python-src"


def test_hook_classification():
    c = classify_file(".claude/hooks/claude-hook.sh")
    assert c.category == "hook"
    assert c.quality_target == "hook-runtime"


def test_targets_deduped():
    assert required_quality_targets(["src/session_browser/a.py", "src/session_browser/b.py"]) == ["python-src"]
