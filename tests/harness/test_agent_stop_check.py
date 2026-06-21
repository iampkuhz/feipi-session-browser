from scripts.harness.agent_stop_check import parse_git_status_paths, required_targets


def test_parse_git_status_paths_includes_deleted_contract_file():
    output = ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    assert parse_git_status_paths(output) == [
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md'
    ]


def test_deleted_contract_file_requires_acceptance_contract_gate():
    output = ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    paths = parse_git_status_paths(output)
    assert required_targets(paths) == ['acceptance-contracts']


def test_parse_git_status_paths_includes_renames():
    output = 'R  docs/old.md -> docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    assert parse_git_status_paths(output) == [
        'docs/old.md',
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
    ]
