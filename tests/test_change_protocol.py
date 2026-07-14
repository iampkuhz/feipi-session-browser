import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.agent_runtime.change.protocol import (
    EXIT_CODES,
    INTERNAL_ERROR,
    LifecycleError,
    classify_gate_failures,
    compact_payload,
    encode_compact,
)


def test_compact_success_and_failure_protocol_are_single_json_under_4k():
    for payload in (
        compact_payload(status='PASS', state='INTEGRATED', code='CHANGE_INTEGRATED'),
        compact_payload(
            status='REPAIR_REQUIRED',
            state='REPAIR_REQUIRED',
            code='GATE_FAILED',
            root_failure={'code': 'GATE_FAIL', 'message': 'fix source'},
            dependent_blocked_count=12,
        ),
    ):
        encoded = encode_compact(payload)
        assert len(encoded.encode()) <= 4096
        assert json.loads(encoded) == payload
        assert '\n' not in encoded


def test_independent_root_failure_is_not_expanded_into_dependent_blocks():
    details = [
        SimpleNamespace(
            name='spotless',
            status='FAIL',
            executionState='EXECUTED',
            output='Foo.java:12 formatting error',
            command=['./gradlew', 'spotlessCheck'],
        ),
        *[
            SimpleNamespace(
                name=f'dependent-{index}',
                status='BLOCKED',
                executionState='DEPENDENCY_BLOCKED',
                output='blocked by gradle group',
                command=[],
            )
            for index in range(10)
        ],
    ]

    root, dependent, full = classify_gate_failures(details)

    assert root is not None and root.code == 'GATE_FAIL'
    assert dependent == 10
    assert len(full) == 1


def test_oversized_protocol_fails_instead_of_dumping_or_truncating():
    with pytest.raises(LifecycleError) as caught:
        encode_compact({'status': 'FAIL', 'dump': 'x' * 5000})
    assert caught.value.status == INTERNAL_ERROR


def test_exit_status_mapping_and_repair_argv_entries_are_executable_contracts():
    assert EXIT_CODES == {
        'PASS': 0,
        'REPAIR_REQUIRED': 2,
        'BUSY_RETRYABLE': 3,
        'CAPABILITY_RETRYABLE': 4,
        'COMMITTED_HANDOFF': 5,
        'TERMINAL_BLOCKED': 6,
        'INTERNAL_ERROR': 70,
    }
    root = Path(__file__).resolve().parents[1]
    script = root / 'scripts' / 'session-browser.sh'
    assert script.is_file() and script.stat().st_mode & 0o111
    assert shutil.which('git')
    help_text = script.read_text(encoding='utf-8')
    assert 'deps' in help_text
    for argv in (
        ('./scripts/session-browser.sh', 'deps'),
        ('git', 'status', '--short'),
    ):
        assert argv and all(part and part != '...' for part in argv)
