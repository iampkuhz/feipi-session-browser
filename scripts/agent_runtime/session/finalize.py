"""负责在重新验证后执行 ff-only 本地集成并生成 handoff；不负责绕过 Stop 或远端推送；由 sessionctl finalize 入口调用。"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.stop.evidence import GitEvidenceError
from scripts.agent_runtime.storage import utc_now as now_utc
from scripts.agent_runtime.storage import write_json_atomic
from scripts.gates.catalog import CATALOG_VERSION
from scripts.gates.planner import plan as build_gate_plan
from scripts.gates.receipt import read_receipt

from .common import _append_run_audit, _set_run_status, emit_json
from .contract import ensure_private_directory
from .handoff import build_handoff_report
from .lease import heartbeat_writer_lease, release_writer_lease
from .lifecycle import _checkout_fingerprint, _collect_git_facts, repo_root_from_arg
from .registry import REGISTRY_VERSION, Registry

if TYPE_CHECKING:
    import argparse


def _write_handoff(registry: Registry, record: dict[str, Any], reason: str) -> Path:
    try:
        facts: dict[str, Any] = _collect_git_facts(record)
    except GitEvidenceError as exc:
        facts = {'queryErrors': [str(exc)], 'gitFactErrors': [str(exc)]}
    report = build_handoff_report(registry, record, facts, reason=reason)
    path = registry.root / 'integration' / f"{record['runId']}.handoff.json"
    write_json_atomic(path, report)
    return path


def _mark_handoff(registry: Registry, record: dict[str, Any], reason: str) -> None:
    path = _write_handoff(registry, record, reason)
    if record.get('status') != 'HANDOFF_REQUIRED':
        _set_run_status(record, 'HANDOFF_REQUIRED')
    record['handoffSummary'] = str(path)
    completion = record.get('completion')
    if isinstance(completion, dict) and completion.get('commitSha'):
        completion['state'] = 'HANDOFF_REQUIRED'
        completion['reason'] = reason
    timestamp = now_utc()
    record['updatedAt'] = timestamp
    _append_run_audit(
        registry,
        record,
        {
            'event': 'FINALIZE_HANDOFF_REQUIRED',
            'runId': record['runId'],
            'sessionId': record['sessionId'],
            'worktreeId': record['worktreeId'],
            'reason': reason,
            'at': timestamp,
        },
    )
    registry.save_run(record)


def _finalize_handoff(registry: Registry, run_id: str, reason: str) -> int:
    with registry.locked():
        record = registry.load_run(run_id)
        _mark_handoff(registry, record, reason)
    if record.get('writerLease'):
        release_writer_lease(registry, record, reason='finalize-handoff')
    completion = record.get('completion')
    commit_sha = str(completion.get('commitSha') or '') if isinstance(completion, Mapping) else ''
    emit_json(
        {
            'status': 'COMMITTED_HANDOFF_REQUIRED' if commit_sha else 'HANDOFF_REQUIRED',
            'runId': run_id,
            'commitSha': commit_sha,
            'resultRef': str(completion.get('resultRef') or '')
            if isinstance(completion, Mapping)
            else '',
            'reason': reason,
        }
    )
    return 2


def _git_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return bool(
        ancestor
        and descendant
        and (
            git(repo, 'merge-base', '--is-ancestor', ancestor, descendant, check=False).returncode
            == 0
        )
    )


def _fresh_validation_error(
    record: Mapping[str, Any], facts: Mapping[str, Any], *, require_target_match: bool
) -> str:
    completion = record.get('completion')
    if isinstance(completion, Mapping) and completion.get('commitSha'):
        attestation = completion.get('commitAttestation')
        integration_attestation = completion.get('integrationAttestation')
        validation = completion.get('validationReceipt')
        checkout = Path(str(record.get('checkoutRoot') or ''))
        commit_sha = str(completion.get('commitSha') or '')
        candidate_tree = str(completion.get('candidateTree') or '')
        if (
            isinstance(integration_attestation, Mapping)
            and integration_attestation.get('status') == 'PASS'
            and str(facts.get('headCommit') or '')
            == str(completion.get('integrationCandidateSha') or '')
            and git(checkout, 'rev-parse', 'HEAD^{tree}').stdout.strip()
            == str(integration_attestation.get('commitTree') or '')
            and int(completion.get('postCommitHeavyProcessCount') or 0) == 0
        ):
            return ''
        if (
            isinstance(attestation, Mapping)
            and attestation.get('status') == 'PASS'
            and isinstance(validation, Mapping)
            and validation.get('status') == 'PASS'
            and str(facts.get('headCommit') or '') == commit_sha
            and git(checkout, 'rev-parse', 'HEAD^{tree}').stdout.strip() == candidate_tree
            and int(completion.get('postCommitHeavyProcessCount') or 0) == 0
        ):
            if require_target_match and str(validation.get('targetCommit') or '') != str(
                facts.get('targetHead') or ''
            ):
                return 'target branch changed after candidate validation'
            return ''
    if record.get('status') != 'VALIDATED' or record.get('stopExitCode') != 0:
        return 'required gates are not fresh PASS'
    validation = record.get('stopValidation')
    if not isinstance(validation, Mapping) or validation.get('status') != 'PASS':
        return 'required gates are not fresh PASS'
    if validation.get('fresh') is not True:
        return 'Stop validation is stale'
    if str(validation.get('headCommit') or '') != str(facts.get('headCommit') or ''):
        return 'checkout HEAD changed after Stop validation'
    if str(validation.get('checkoutFingerprint') or '') != _checkout_fingerprint(facts):
        validated_checkout = str(validation.get('checkoutContentFingerprint') or '')
        current_checkout = str(facts.get('checkoutContentFingerprint') or '')
        if not validated_checkout or validated_checkout != current_checkout:
            return 'checkout Git state changed after Stop validation'
        validated_primary = str(validation.get('primaryFingerprint') or '')
        current_primary = str(facts.get('primaryFingerprint') or '')
        primary_status = facts.get('primaryStatus')
        target_advanced_cleanly = bool(
            not require_target_match
            and isinstance(primary_status, Mapping)
            and (primary_status.get('clean') is True)
            and (str(primary_status.get('headCommit') or '') == str(facts.get('targetHead') or ''))
            and (str(validation.get('targetCommit') or '') != str(facts.get('targetHead') or ''))
        )
        if (
            not validated_primary
            or validated_primary == current_primary
            or (not target_advanced_cleanly)
        ):
            return 'primary checkout changed after Stop validation'
    if require_target_match and str(validation.get('targetCommit') or '') != str(
        facts.get('targetHead') or ''
    ):
        return 'target branch changed after Stop validation'
    return ''


def _target_delta_reuse_error(
    record: Mapping[str, Any], target_delta: set[str]
) -> tuple[str, list[dict[str, str]]]:
    """只允许 catalog 证明为无 target 的 disjoint delta 复用既有强 receipt。"""
    completion = record.get('completion')
    if not isinstance(completion, Mapping) or not completion.get('commitSha'):
        return 'target advanced without an attested completion commit', []
    exact_files = set(completion.get('exactFiles') or [])
    if target_delta & exact_files:
        return 'target advanced and overlapped exact candidate files', []
    sensitive = {
        path
        for path in target_delta
        if path == 'config/gates.yaml'
        or path.startswith('scripts/gates/')
        or path in {'pyproject.toml', 'uv.lock', 'package.json', 'package-lock.json'}
        or path.endswith('.gradle.kts')
    }
    if sensitive:
        return 'target advanced and changed catalog/command/environment inputs', []
    delta_plan = build_gate_plan(sorted(target_delta), tier='required')
    if delta_plan.effective_targets:
        return 'target advanced and selected affected required Gate targets', []
    validation = completion.get('validationReceipt')
    paths = validation.get('gateReceiptPaths') if isinstance(validation, Mapping) else None
    if not isinstance(paths, list) or not paths:
        return 'target advance reuse requires non-empty PASS receipts', []
    fingerprints: list[dict[str, str]] = []
    for raw in paths:
        receipt = read_receipt(Path(str(raw)))
        if not receipt or receipt.get('status') != 'PASS':
            return 'target advance receipt is missing or not PASS', []
        if receipt.get('catalog_version') != CATALOG_VERSION:
            return 'target advance changed the Gate catalog identity', []
        required = {
            key: str(receipt.get(key) or '')
            for key in (
                'cache_key',
                'plan_fingerprint',
                'command_fingerprint',
                'environment_fingerprint',
                'gate_input_fingerprint',
            )
        }
        if not all(required.values()):
            return 'target advance receipt lacks bound Gate inputs', []
        fingerprints.append(required)
    return '', fingerprints


def _tree_entry(repo: Path, commit: str, path: str) -> str:
    return git(repo, 'ls-tree', '-z', commit, '--', path).stdout


def cmd_finalize(args: argparse.Namespace) -> int:
    """重新验证 Stop 回执与 Git 指纹后执行 ff-only 集成；任何竞态都转为 handoff。"""
    selected_checkout = repo_root_from_arg(args.repo_root)
    registry = Registry(selected_checkout)
    lock_dir = ensure_private_directory(registry.root / 'locks', root=registry.root)
    lock_path = lock_dir / 'integration.lock'
    with lock_path.open('a+', encoding='utf-8') as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        with registry.locked():
            record = registry.load_run(args.run_id)
        if record.get('status') == 'INTEGRATED':
            emit_json({'status': 'INTEGRATED', 'runId': args.run_id, 'idempotent': True})
            return 0
        checkout = Path(str(record.get('checkoutRoot') or ''))
        primary = Path(str(record.get('primaryRepoRoot') or ''))
        target = str(record.get('targetBranch') or '')
        if not checkout.exists():
            return _finalize_handoff(registry, args.run_id, 'run checkout missing')
        if not primary.exists():
            return _finalize_handoff(registry, args.run_id, 'primary checkout missing')
        if not target:
            return _finalize_handoff(registry, args.run_id, 'missing target branch')
        if git(primary, 'check-ref-format', '--branch', target, check=False).returncode != 0:
            return _finalize_handoff(registry, args.run_id, 'invalid target branch')
        try:
            facts = _collect_git_facts(record)
        except GitEvidenceError as exc:
            return _finalize_handoff(registry, args.run_id, f'Git evidence unavailable: {exc}')
        initial_dirty = record.get('initialDirtySnapshot')
        begin = record.get('changeBegin')
        adopted = isinstance(begin, Mapping) and begin.get('adopted') is True
        if not isinstance(initial_dirty, Mapping) or (initial_dirty.get('dirty') and not adopted):
            return _finalize_handoff(
                registry, args.run_id, 'initial dirty baseline cannot be safely attributed'
            )
        if not facts['targetStatus']['exists']:
            return _finalize_handoff(registry, args.run_id, 'target branch is missing')
        if facts['primaryStatus']['branch'] != target:
            return _finalize_handoff(
                registry, args.run_id, 'primary checkout is not on the recorded target branch'
            )
        if not facts['primaryStatus']['clean']:
            return _finalize_handoff(registry, args.run_id, 'primary checkout dirty')
        if not facts['checkoutStatus']['clean']:
            return _finalize_handoff(
                registry, args.run_id, 'run checkout has uncommitted or untracked files'
            )
        validation_error = _fresh_validation_error(record, facts, require_target_match=False)
        if validation_error:
            return _finalize_handoff(registry, args.run_id, validation_error)
        original_run_head = str(facts['headCommit'])
        validated_target = str(record['stopValidation'].get('targetCommit') or '')
        target_old = str(facts['targetHead'])
        strategy = 'ff-only'
        if validated_target != target_old:
            if not _git_is_ancestor(checkout, validated_target, target_old):
                return _finalize_handoff(
                    registry,
                    args.run_id,
                    'target branch was rewritten or moved backwards after validation',
                )
            if not _git_is_ancestor(checkout, target_old, original_run_head):
                base = str(record.get('baseCommit') or '')
                if not (
                    _git_is_ancestor(checkout, base, target_old)
                    and _git_is_ancestor(checkout, base, original_run_head)
                ):
                    return _finalize_handoff(
                        registry, args.run_id, 'target and result ancestry cannot be safely rebased'
                    )
                target_delta = set(
                    git(
                        checkout,
                        'diff',
                        '--name-only',
                        '--no-renames',
                        validated_target,
                        target_old,
                    ).stdout.splitlines()
                )
                reuse_error, receipt_fingerprints = _target_delta_reuse_error(record, target_delta)
                if reuse_error:
                    return _finalize_handoff(
                        registry,
                        args.run_id,
                        reuse_error,
                    )
                strategy = 'target-delta-reuse-then-ff'
                target_ref = f'refs/heads/{target}'
                rebase = git(checkout, 'rebase', target_ref, check=False)
                if rebase.returncode != 0:
                    git(checkout, 'rebase', '--abort', check=False)
                    return _finalize_handoff(
                        registry, args.run_id, 'target advanced with conflicts'
                    )
                rebased_head = git(checkout, 'rev-parse', 'HEAD').stdout.strip()
                completion = record.get('completion')
                if isinstance(completion, dict):
                    old_commit = str(completion.get('commitSha') or '')
                    result_ref = str(completion.get('resultRef') or '')
                    exact_files = set(completion.get('exactFiles') or [])
                    committed_paths = set(
                        git(
                            checkout,
                            'diff-tree',
                            '--no-commit-id',
                            '--name-only',
                            '--no-renames',
                            '-r',
                            rebased_head,
                        ).stdout.splitlines()
                    )
                    entries_match = all(
                        _tree_entry(checkout, old_commit, path)
                        == _tree_entry(checkout, rebased_head, path)
                        for path in exact_files
                    )
                    if (
                        committed_paths != exact_files
                        or not entries_match
                        or git(checkout, 'rev-parse', f'{rebased_head}^').stdout.strip()
                        != target_old
                        or not result_ref
                        or git(checkout, 'rev-parse', result_ref).stdout.strip() != old_commit
                    ):
                        return _finalize_handoff(
                            registry,
                            args.run_id,
                            'rebased integration candidate failed lightweight attestation',
                        )
                    integration_ref = f'refs/heads/codex/integration/{args.run_id}'
                    existing_integration_ref = git(
                        checkout, 'rev-parse', '--verify', integration_ref, check=False
                    ).stdout.strip()
                    if existing_integration_ref and existing_integration_ref != rebased_head:
                        return _finalize_handoff(
                            registry,
                            args.run_id,
                            'integration ref already points to another commit',
                        )
                    if not existing_integration_ref:
                        update = git(
                            checkout,
                            'update-ref',
                            integration_ref,
                            rebased_head,
                            '0' * 40,
                            check=False,
                        )
                        if update.returncode != 0:
                            return _finalize_handoff(
                                registry, args.run_id, 'integration result ref creation failed'
                            )
                    integration_tree = git(checkout, 'rev-parse', 'HEAD^{tree}').stdout.strip()
                    completion['integrationCandidateSha'] = rebased_head
                    completion['integrationRef'] = integration_ref
                    completion['validationReuse'] = {
                        'status': 'REUSED',
                        'reason': 'target-delta-has-no-effective-target-and-bound-inputs-unchanged',
                        'targetDelta': sorted(target_delta),
                        'receiptFingerprints': receipt_fingerprints,
                        'heavyGateRuns': 0,
                    }
                    completion['integrationAttestation'] = {
                        'status': 'PASS',
                        'originalCommitSha': old_commit,
                        'originalResultRef': result_ref,
                        'integrationCommitSha': rebased_head,
                        'integrationRef': integration_ref,
                        'commitTree': integration_tree,
                        'parent': target_old,
                        'committedPaths': sorted(committed_paths),
                        'exactEntriesPreserved': entries_match,
                        'heavyProcessCount': 0,
                        'targetDeltaReuse': True,
                    }
                    record['headCommit'] = rebased_head
                    with registry.locked():
                        registry.save_run(record)
            else:
                strategy = 'target-already-in-result-history'
            with registry.locked():
                record = registry.load_run(args.run_id)
            try:
                facts = _collect_git_facts(record)
            except GitEvidenceError as exc:
                return _finalize_handoff(
                    registry, args.run_id, f'Git evidence unavailable after revalidation: {exc}'
                )
        run_head = str(facts['headCommit'])
        target_old = str(facts['targetHead'])
        if not _git_is_ancestor(checkout, target_old, run_head):
            return _finalize_handoff(
                registry, args.run_id, 'result is not a fast-forward of target'
            )
        if record.get('writerLease'):
            heartbeat_writer_lease(registry, record)
        with registry.locked():
            record = registry.load_run(args.run_id)
            _set_run_status(record, 'INTEGRATING')
            record['headCommit'] = run_head
            record['updatedAt'] = now_utc()
            registry.save_run(record)
        try:
            before_merge = _collect_git_facts(record)
        except GitEvidenceError as exc:
            return _finalize_handoff(
                registry, args.run_id, f'Git evidence changed before integration: {exc}'
            )
        if (
            before_merge['targetHead'] != target_old
            or before_merge['primaryStatus']['branch'] != target
            or (not before_merge['primaryStatus']['clean'])
            or (not before_merge['checkoutStatus']['clean'])
            or (before_merge['headCommit'] != run_head)
        ):
            return _finalize_handoff(registry, args.run_id, 'Git state changed before integration')
        same_checkout = checkout.resolve() == primary.resolve()
        if same_checkout:
            if target_old != run_head:
                return _finalize_handoff(
                    registry, args.run_id, 'primary checkout target does not match validated HEAD'
                )
            strategy = 'already-on-target'
        else:
            merge = git(primary, 'merge', '--ff-only', run_head, check=False)
            if merge.returncode != 0:
                return _finalize_handoff(registry, args.run_id, 'ff-only integration failed')
        target_new_result = git(
            primary, 'rev-parse', '--verify', f'refs/heads/{target}', check=False
        )
        target_new = target_new_result.stdout.strip() if target_new_result.returncode == 0 else ''
        if target_new != run_head:
            return _finalize_handoff(
                registry, args.run_id, 'target did not reach the validated result'
            )
        with registry.locked():
            record = registry.load_run(args.run_id)
        if record.get('writerLease'):
            record, _ = release_writer_lease(registry, record, reason='finalize-integrated')
        timestamp = now_utc()
        summary = {
            'schemaVersion': REGISTRY_VERSION,
            'status': 'INTEGRATED',
            'runId': args.run_id,
            'oldTarget': target_old,
            'baseCommit': record.get('baseCommit'),
            'originalRunHead': original_run_head,
            'integratedHead': target_new,
            'strategy': strategy,
            'checkoutRoot': str(checkout),
            'checkoutKind': record.get('checkoutKind', ''),
            'checkoutCreator': record.get('checkoutCreator', 'unknown'),
            'checkoutPreserved': checkout.exists(),
            'pushed': False,
            'artifacts': record.get('qualityArtifacts', []),
            'integratedAt': timestamp,
        }
        summary_path = registry.root / 'integration' / f'{args.run_id}.json'
        write_json_atomic(summary_path, summary)
        with registry.locked():
            record = registry.load_run(args.run_id)
            _set_run_status(record, 'INTEGRATED')
            record['headCommit'] = target_new
            completion = record.get('completion')
            if isinstance(completion, dict):
                completion['state'] = 'INTEGRATED'
                completion['integratedCommitSha'] = target_new
                completion['targetHeadObserved'] = target_new
            record['integrationSummary'] = str(summary_path)
            record['updatedAt'] = timestamp
            _append_run_audit(
                registry,
                record,
                {
                    'event': 'RUN_INTEGRATED',
                    'runId': record['runId'],
                    'sessionId': record['sessionId'],
                    'worktreeId': record['worktreeId'],
                    'targetBranch': target,
                    'targetCommit': target_new,
                    'strategy': strategy,
                    'checkoutPreserved': True,
                    'at': timestamp,
                },
            )
            registry.save_run(record)
        emit_json(summary)
        return 0
