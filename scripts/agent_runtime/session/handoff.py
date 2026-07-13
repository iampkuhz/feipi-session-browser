"""负责统一构造 Session handoff 的 Git、checkout 与失败字段；不负责修改运行状态；由 lifecycle 和 finalize 调用。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .registry import REGISTRY_VERSION, Registry

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_RECORD_FIELDS = (
    'runId taskId client sessionId worktreeId checkoutRoot branch primaryRepoRoot '
    'baseCommit targetBranch changeId checkoutKind checkoutCreator'
).split()
_GIT_FIELDS = (
    'mergeBase headCommit changedFiles committedFiles uncommittedFiles untrackedFiles commits '
    'aheadBehind initialDirtyBaseline targetStatus primaryStatus'
).split()


def build_handoff_report(
    registry: Registry,
    record: Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    reason: str = '',
    scope_overlaps: Iterable[str] = (),
    blocking_failures: Iterable[str] = (),
) -> dict[str, Any]:
    """投影稳定 handoff schema；调用方只负责收集事实和选择持久化/展示。"""
    overlaps = list(scope_overlaps)
    report = {field: record.get(field, '') for field in _RECORD_FIELDS}
    report.update({field: facts.get(field, []) for field in _GIT_FIELDS})
    report.update(
        {
            'schemaVersion': REGISTRY_VERSION,
            'status': 'HANDOFF_REQUIRED' if reason else record.get('status', ''),
            'reason': reason,
            'observedBranch': facts.get('checkout', {}).get('branch', ''),
            'detached': bool(facts.get('checkout', {}).get('detached')),
            'gitCommonDir': facts.get('checkout', {}).get('gitCommonDir', ''),
            'gitFacts': dict(facts),
            'requiredGateStatus': record.get('stopExitCode', 'unknown'),
            'requiredTargetSummary': record.get(
                'requiredTargetSummary',
                {
                    'allowedPaths': record.get('allowedPaths', []),
                    'forbiddenPaths': record.get('forbiddenPaths', []),
                },
            ),
            'qualityArtifacts': record.get('qualityArtifacts', []),
            'artifactPaths': {
                'runRecord': str(registry._run_path(str(record['runId']))),
                'runtimeRoot': str(registry.root),
                'checkoutRoot': record['checkoutRoot'],
            },
            'blockingFailures': list(blocking_failures),
            'mergeRisk': {
                'reason': reason,
                'writeScopeOverlap': overlaps,
                'dirtyWorktree': not facts.get('checkoutStatus', {}).get('clean', False),
                'initialDirtyAmbiguous': bool(
                    isinstance(record.get('initialDirtySnapshot'), dict)
                    and record['initialDirtySnapshot'].get('dirty')
                ),
            },
            'risks': list(record.get('risks', [])) + overlaps,
            'finalizeCommand': (
                f"python3 scripts/harness/sessionctl.py finalize --run-id {record['runId']}"
            ),
        }
    )
    report['manualNextSteps'] = [
        'review changedFiles and blockingFailures',
        'run required gates before merge',
        report['finalizeCommand'],
        "release only this run's lease; the provider-owned checkout is preserved",
    ]
    return report
