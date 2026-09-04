"""负责持久化不可覆盖、可复现的 schema v5 Gate 运行证据；不负责结果分类。

由 CLI 在 Execution 阶段完成后调用。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from scripts.gates.execution import GateResult, InvocationResult, StepResult
    from scripts.gates.planning import CommandInvocation, GatePlan

SCHEMA_VERSION = 5
_EXECUTION_STATUSES = frozenset({'PASS', 'BLOCKED', 'FAIL'})
_SECRET_KEY = re.compile(r'(?i)(credential|password|secret|token|api[_-]?key)')
_SAFE_NAME = re.compile(r'[^A-Za-z0-9._-]+')


@dataclass(frozen=True, slots=True)
class RunReceipt:
    """表示一次完整运行及其不可变 artifact 位置。"""

    schema_version: int
    run_id: str
    status: str
    reason: str
    started_at: str
    finished_at: str
    duration_ms: int
    plan_fingerprint: str
    run_directory: Path
    plan_path: Path
    summary_path: Path
    log_paths: tuple[Path, ...]
    canonical_rerun: str
    plan: GatePlan
    gate_results: tuple[GateResult, ...]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _redacted_environment(environment: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {
        str(key): '<redacted>' if _SECRET_KEY.search(str(key)) else str(value)
        for key, value in environment
    }


def _snapshot_payload(plan: GatePlan) -> dict[str, Any]:
    snapshot = plan.snapshot
    return {
        'source': snapshot.source,
        'head': snapshot.head,
        'base': snapshot.base,
        'files': list(snapshot.files),
        'contentFingerprint': snapshot.content_fingerprint,
    }


def _invocation_payload(invocation: CommandInvocation) -> dict[str, Any]:
    return {
        'invocationId': invocation.invocation_id,
        'kind': invocation.kind,
        'argv': list(invocation.argv),
        'environment': _redacted_environment(invocation.environment),
        'gate': invocation.gate_name,
        'recipeStep': invocation.recipe_step_name,
    }


def _plan_payload(plan: GatePlan) -> dict[str, Any]:
    gates = []
    for gate in plan.gates:
        gates.append(
            {
                'gate': gate.name,
                'description': gate.description,
                'durationTargetSeconds': gate.recipe.duration_for(plan.mode),
                'recipeSteps': [
                    {'name': step.name, 'kind': step.kind.value} for step in gate.recipe.steps
                ],
            }
        )
    return {
        'schemaVersion': SCHEMA_VERSION,
        'kind': 'gate-plan',
        'mode': plan.mode.value,
        'snapshot': _snapshot_payload(plan),
        'selector': (
            {'kind': plan.selector_kind, 'value': plan.selector_value}
            if plan.selector_kind and plan.selector_value
            else None
        ),
        'matches': [
            {'file': item.file, 'pattern': item.pattern, 'gate': item.gate_name}
            for item in plan.matches
        ],
        'notTriggered': [
            {'gate': item.gate_name, 'reason': item.reason} for item in plan.not_triggered
        ],
        'gates': gates,
        'commandInvocations': [_invocation_payload(item) for item in plan.command_invocations],
        'processCount': plan.process_count,
    }


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _safe_log_name(value: str) -> str:
    normalized = _SAFE_NAME.sub('-', value).strip('.-')
    return normalized[:120] or 'owner'


def _write_step_logs(
    run_directory: Path, gate_results: tuple[GateResult, ...]
) -> tuple[dict[int, str], list[Path]]:
    relative_by_step: dict[int, str] = {}
    paths: list[Path] = []
    step_index = 0
    for gate in gate_results:
        for step in gate.step_results:
            for invocation in step.invocation_results:
                filename = _safe_log_name(
                    f'{step_index:02d}-{invocation.gate_name}-'
                    f'{invocation.recipe_step_name}-{invocation.invocation_id}.log'
                )
                path = run_directory / 'logs' / filename
                log_source = invocation.log_path
                content = (
                    Path(log_source).read_bytes()
                    if log_source and Path(log_source).is_file()
                    else invocation.output_tail.encode()
                )
                with path.open('xb') as stream:
                    stream.write(content)
                relative_by_step[id(invocation)] = str(path.relative_to(run_directory))
                paths.append(path)
                step_index += 1
    return relative_by_step, paths


def _write_additional_logs(run_directory: Path, sources: Mapping[str, Path]) -> list[Path]:
    paths: list[Path] = []
    for label, source in sources.items():
        filename = _safe_log_name(label)
        filename = filename if filename.endswith('.log') else f'{filename}.log'
        path = run_directory / 'logs' / filename
        with path.open('xb') as stream:
            stream.write(source.read_bytes() if source.is_file() else b'')
        paths.append(path)
    return paths


def _duration_ms(seconds: float) -> int:
    return max(0, round(seconds * 1000))


def _invocation_result_payload(
    result: InvocationResult, log_paths: Mapping[int, str]
) -> dict[str, Any]:
    return {
        'invocationId': result.invocation_id,
        'status': result.status.value,
        'reason': result.reason,
        'returnCode': result.return_code,
        'durationMs': _duration_ms(result.duration_seconds),
        'logPath': log_paths.get(id(result), ''),
        'taskOutcomes': dict(result.task_outcomes),
        'taskFailureReasons': dict(result.task_failure_reasons),
    }


def _step_payload(step: StepResult, log_paths: Mapping[int, str]) -> dict[str, Any]:
    return {
        'gate': step.gate_name,
        'recipeStep': step.recipe_step_name,
        'status': step.status.value,
        'reason': step.reason,
        'durationMs': _duration_ms(step.duration_seconds),
        'invocationResults': [
            _invocation_result_payload(item, log_paths) for item in step.invocation_results
        ],
        'canonicalRerun': step.canonical_rerun,
    }


def _gate_payload(
    gate_result: GateResult, log_paths: Mapping[int, str], fallback_rerun: str
) -> dict[str, Any]:
    """把单个 GateResult 转成稳定的 schema v5 证据结构。"""
    return {
        'gate': gate_result.gate_name,
        'status': gate_result.status.value,
        'reason': gate_result.reason,
        'durationMs': _duration_ms(gate_result.duration_seconds),
        'targetSeconds': gate_result.target_seconds,
        'timingState': gate_result.timing_state,
        'recipeSteps': [_step_payload(step, log_paths) for step in gate_result.step_results],
        'canonicalRerun': fallback_rerun,
    }


def _overall_status(gate_results: tuple[GateResult, ...], reason: str) -> tuple[str, str]:
    results = tuple(gate_results)
    statuses = [item.status.value for item in results]
    if not statuses:
        return 'FAIL', reason or 'outcome-unknown'
    if any(status not in _EXECUTION_STATUSES for status in statuses):
        return 'FAIL', reason or 'outcome-unknown'
    if 'FAIL' in statuses:
        failed = results[statuses.index('FAIL')]
        return 'FAIL', reason or failed.reason or 'outcome-unknown'
    if 'BLOCKED' in statuses:
        return 'BLOCKED', reason or 'verification-failed'
    return 'PASS', ''


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _canonical_rerun(plan: GatePlan) -> str:
    command = ['python3', 'scripts/gates/cli.py', 'run', '--mode', plan.mode.value]
    if plan.selector_kind and plan.selector_value:
        command.extend([f'--{plan.selector_kind}', plan.selector_value])
    if plan.mode.value == 'incremental':
        if plan.snapshot.source == 'git-base' and plan.snapshot.base:
            command.extend(['--base', plan.snapshot.base])
        else:
            command.extend(
                ['--changed-files', json.dumps(list(plan.snapshot.files), separators=(',', ':'))]
            )
    return shlex.join(command)


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')
    return f'{stamp}-{uuid.uuid4().hex[:8]}'


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')


def _update_latest(runs_root: Path, run_id: str, summary_path: Path) -> None:
    latest = runs_root / 'latest.json'
    temporary = runs_root / f'.latest-{uuid.uuid4().hex}.tmp'
    temporary.write_text(
        json.dumps(
            {'runId': run_id, 'summary': str(summary_path.relative_to(runs_root))},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + '\n',
        encoding='utf-8',
    )
    os.replace(temporary, latest)


def store_run_receipt(
    plan: GatePlan,
    gate_results: Iterable[GateResult],
    *,
    repo_root: Path,
    runs_root: Path | None = None,
    run_id: str | None = None,
    reason: str = '',
    started_at: str | None = None,
    finished_at: str | None = None,
    additional_logs: Mapping[str, Path] | None = None,
) -> RunReceipt:
    """新建一次 schema v5 run；同名 run 永不覆盖。"""

    results = tuple(gate_results)
    started = started_at or _utc_now()
    finished = finished_at or _utc_now()
    selected_run_id = run_id or _new_run_id()
    if not selected_run_id or _SAFE_NAME.sub('', selected_run_id) != selected_run_id:
        raise ValueError(f'invalid run id: {selected_run_id!r}')

    root = runs_root or repo_root / 'tmp' / 'quality' / 'runs'
    root.mkdir(parents=True, exist_ok=True)
    run_directory = root / selected_run_id
    run_directory.mkdir()
    (run_directory / 'logs').mkdir()

    plan_payload = _plan_payload(plan)
    plan_fingerprint = _fingerprint(plan_payload)
    plan_payload['planFingerprint'] = plan_fingerprint
    canonical_rerun = _canonical_rerun(plan)
    log_paths_by_step, log_paths = _write_step_logs(run_directory, results)
    log_paths.extend(_write_additional_logs(run_directory, additional_logs or {}))
    status, final_reason = _overall_status(results, reason)
    gate_payloads = [
        _gate_payload(
            result,
            log_paths_by_step,
            shlex.join(
                [
                    'python3',
                    'scripts/gates/cli.py',
                    'run',
                    '--mode',
                    'full',
                    '--gate',
                    result.gate_name,
                ]
            ),
        )
        for result in results
    ]
    duration_ms = max(0, int((_parse_time(finished) - _parse_time(started)).total_seconds() * 1000))
    summary_payload = {
        'schemaVersion': SCHEMA_VERSION,
        'kind': 'gate-run-receipt',
        'runId': selected_run_id,
        'status': status,
        'reason': final_reason,
        'mode': plan.mode.value,
        'startedAt': started,
        'finishedAt': finished,
        'durationMs': duration_ms,
        'planFingerprint': plan_fingerprint,
        'snapshot': _snapshot_payload(plan),
        'selector': plan_payload['selector'],
        'matches': plan_payload['matches'],
        'notTriggered': plan_payload['notTriggered'],
        'commandInvocations': plan_payload['commandInvocations'],
        'processCount': plan.process_count,
        'gateResults': gate_payloads,
        'canonicalRerun': canonical_rerun,
        'artifacts': {
            'plan': 'plan.json',
            'summary': 'summary.json',
            'logs': [str(path.relative_to(run_directory)) for path in log_paths],
        },
    }
    plan_path = run_directory / 'plan.json'
    summary_path = run_directory / 'summary.json'
    _write_json_exclusive(plan_path, plan_payload)
    _write_json_exclusive(summary_path, summary_payload)
    _update_latest(root, selected_run_id, summary_path)
    return RunReceipt(
        schema_version=SCHEMA_VERSION,
        run_id=selected_run_id,
        status=status,
        reason=final_reason,
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        plan_fingerprint=plan_fingerprint,
        run_directory=run_directory,
        plan_path=plan_path,
        summary_path=summary_path,
        log_paths=tuple(log_paths),
        canonical_rerun=canonical_rerun,
        plan=plan,
        gate_results=results,
    )
