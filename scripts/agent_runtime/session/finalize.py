"""负责在重新验证后执行 ff-only 本地集成并生成 handoff；不负责绕过 Stop 或远端推送；由 sessionctl finalize 入口调用。"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import io
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.agent_runtime.git_state import run as git
from scripts.agent_runtime.stop.evidence import GitEvidenceError
from scripts.agent_runtime.storage import utc_now as now_utc
from scripts.agent_runtime.storage import write_json_atomic

from .common import _append_run_audit, _set_run_status, emit_json
from .contract import ensure_private_directory
from .handoff import build_handoff_report
from .lease import heartbeat_writer_lease, release_writer_lease
from .lifecycle import _checkout_fingerprint, _collect_git_facts, cmd_stop, repo_root_from_arg
from .registry import REGISTRY_VERSION, Registry


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
    emit_json({'status': 'HANDOFF_REQUIRED', 'runId': run_id, 'reason': reason})
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


def _revalidate_for_finalize(registry: Registry, record: Mapping[str, Any]) -> bool:
    with contextlib.redirect_stdout(io.StringIO()):
        result = cmd_stop(
            argparse.Namespace(
                repo_root=str(registry.primary_repo_root),
                run_id=str(record['runId']),
                handoff_on_failure=True,
            )
        )
    return result == 0


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
        if not isinstance(initial_dirty, Mapping) or initial_dirty.get('dirty'):
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
        if facts['checkoutStatus']['detached']:
            return _finalize_handoff(
                registry,
                args.run_id,
                'detached HEAD requires a provider-owned branch or manual handoff',
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
                strategy = 'rebase-then-ff'
                target_ref = f'refs/heads/{target}'
                rebase = git(checkout, 'rebase', target_ref, check=False)
                if rebase.returncode != 0:
                    git(checkout, 'rebase', '--abort', check=False)
                    return _finalize_handoff(
                        registry, args.run_id, 'target advanced with conflicts'
                    )
            else:
                strategy = 'revalidate-then-ff'
            if not _revalidate_for_finalize(registry, record):
                return _finalize_handoff(
                    registry, args.run_id, 'revalidation failed after target advanced'
                )
            with registry.locked():
                record = registry.load_run(args.run_id)
            try:
                facts = _collect_git_facts(record)
            except GitEvidenceError as exc:
                return _finalize_handoff(
                    registry, args.run_id, f'Git evidence unavailable after revalidation: {exc}'
                )
            validation_error = _fresh_validation_error(record, facts, require_target_match=True)
            if validation_error:
                return _finalize_handoff(registry, args.run_id, validation_error)
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
