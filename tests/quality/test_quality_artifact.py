from scripts.quality.quality_artifact import compute_overall


def test_pass_only_when_all_required_pass():
    assert compute_overall({"a": "PASS", "b": "PASS"}) == ("PASS", [])


def test_skipped_is_failure():
    status, failures = compute_overall({"a": "PASS", "b": "SKIPPED"})
    assert status == "FAIL"
    assert failures


def test_empty_required_is_blocked():
    status, failures = compute_overall({})
    assert status == "BLOCKED"
    assert failures
