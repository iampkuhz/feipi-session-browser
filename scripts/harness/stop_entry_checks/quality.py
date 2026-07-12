"""质量门禁：OpenSpec 验证、直接调用原子 check 脚本、runtime-report 写入与校验。

质量门禁不再通过 run_required_quality_gates.py → run_quality_gate.py 的管道链路，
而是由 stop_entry 直接调用每个 check 脚本。每个 check 脚本通过 --changed-files
参数自感知是否需要运行。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.claude_hooks import paths as runtime_paths
from scripts.harness import stop_helpers
from scripts.quality import check_agent_runtime_report
from scripts.quality._trigger import glob_match
from scripts.quality.quality_targets import (
    QUALITY_TARGETS,
    GATE_PATTERNS,
    target_parallel_meta,
)
from scripts.quality.run_quality_gate import gate_command as _gate_command

from ._io import utc_now


def run_cmd(
    name: str,
    cmd: list[str],
    repo_root: Path,
    env: dict[str, str],
    timeout: int = 1800,
) -> bool:
    """执行子进程并等待完成。"""
    print(f'[stop_entry] running {name}: {" ".join(cmd)}', file=sys.stderr)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=repo_root,
            env=env,
            start_new_session=True,
        )
        try:
            return proc.wait(timeout=timeout) == 0
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            return False
    except Exception as exc:
        print(f'[stop_entry] {name} failed to start: {exc}', file=sys.stderr)
        return False


def _target_artifact_status(report_path: Path, target: str) -> str:
    """读取质量目标产物状态。"""
    artifact = report_path.parent / f'quality-gate-summary.{target}.json'
    try:
        data = json.loads(artifact.read_text(encoding='utf-8'))
    except Exception:
        return 'NOT_RUN'
    status = str(data.get('status') or '').upper()
    return status if status in {'PASS', 'FAIL', 'BLOCKED'} else 'BLOCKED'


def run_openspec_validation(
    change_id: str,
    changed_files: list[str],
    repo_root: Path,
) -> list[str]:
    """执行 OpenSpec active-change 验证。返回 failure 列表。"""
    failures: list[str] = []
    if not stop_helpers.changed_files_require_openspec(changed_files):
        return failures
    if change_id == 'unknown':
        failures.append('active change is missing for protected changes')
        return failures
    env = os.environ.copy()
    if not run_cmd(
        'openspec-active-change',
        [sys.executable, 'scripts/openspec/validate_active_change.py', '--change-id', change_id],
        repo_root,
        env,
        timeout=300,
    ):
        failures.append('validate_active_change.py failed')
    return failures


def _gate_is_applicable(
    gate: str, target: str, changed_files: list[str]
) -> bool:
    """通过 GATE_PATTERNS 判断 gate 是否应被触发。"""
    gate_patterns = GATE_PATTERNS.get(target, {}).get(gate)
    if gate_patterns is None:
        # 无 trigger rule 的 gate 默认运行（增量兜底）
        return True
    return any(
        glob_match(f, pat) for f in changed_files for pat in gate_patterns
    )


def run_quality_checks(
    change_id: str,
    changed_files: list[str],
    repo_root: Path,
    targets: list[str],
) -> tuple[bool, list[str], list[dict[str, str]]]:
    """直接调用原子 check 脚本，不再经过 run_required_quality_gates.py 管道。

    返回 (gates_ok, failures, gate_results)。
    gate_results 格式: [{'name': 'javaCheck', 'status': 'PASS'}, ...]
    """
    failures: list[str] = []
    gate_results: list[dict[str, str]] = []

    env = os.environ.copy()
    for key in list(env):
        if key.startswith('FEIPI_') and key != 'FEIPI_AGENT_RUNTIME_ROOT':
            env.pop(key, None)
    env['ACTIVE_CHANGE_ID'] = change_id
    if changed_files:
        env['QUALITY_CHANGED_FILES'] = json.dumps(changed_files, ensure_ascii=False)

    changed_files_json = json.dumps(changed_files, ensure_ascii=False) if changed_files else '[]'

    # ── 显式 check 清单：按 target 分组，每个 gate 直接调用 ──
    for target in targets:
        gates = QUALITY_TARGETS.get(target, [])
        target_timeout = int(target_parallel_meta(target).get('timeout', 300))

        for gate in gates:
            # 预过滤：用 GATE_PATTERNS 判断是否需要调用此 check
            if changed_files and not _gate_is_applicable(gate, target, changed_files):
                gate_results.append({'name': gate, 'status': 'NOT_TRIGGERED'})
                continue

            # 解析 check 命令
            cmd = _gate_command(gate, repo_root, target)
            if not cmd:
                gate_results.append({'name': gate, 'status': 'BLOCKED'})
                failures.append(f'{gate}: no executable command or dependency missing')
                continue

            # 构建 check 环境变量，注入 --changed-files
            check_env = env.copy()
            check_env['SESSION_BROWSER_PYTHON'] = env.get('SESSION_BROWSER_PYTHON', sys.executable)

            # 直接调用 check 脚本，传入 --changed-files 供其自感知
            cmd_with_trigger = list(cmd)
            if gate not in {'javaCheck', 'scanScriptSmoke'}:
                cmd_with_trigger.extend(['--changed-files', changed_files_json])

            label = ' '.join(cmd[:4]) if len(cmd) > 4 else ' '.join(cmd)
            print(f'[stop_entry] running {gate}: {label}', file=sys.stderr)

            ok = run_cmd(
                gate,
                cmd_with_trigger,
                repo_root,
                check_env,
                timeout=target_timeout,
            )
            status = 'PASS' if ok else 'FAIL'
            gate_results.append({'name': gate, 'status': status})
            if not ok:
                failures.append(f'{gate} failed')

    gates_ok = not failures
    return gates_ok, failures, gate_results


def write_runtime_report(
    path: Path,
    *,
    identity: Any,
    change_id: str,
    changed_files: list[str],
    targets: list[str],
    gates_ok: bool,
    failures: list[str],
    git_evidence: dict[str, Any],
    gate_results: list[dict[str, str]] | None = None,
) -> None:
    """写入运行报告 JSON。"""
    # 使用直接调用结果，而非从 artifact 文件读取
    if gate_results:
        gates = gate_results
    else:
        gates = [
            {'name': target, 'status': _target_artifact_status(path, target)}
            for target in targets
        ]
    if targets and gates_ok:
        for gate in gates:
            if gate['status'] in ('NOT_RUN', 'NOT_TRIGGERED'):
                gate['status'] = 'BLOCKED' if gate['status'] == 'NOT_RUN' else 'PASS'
    blocked = list(failures)
    if targets and not gates_ok and 'quality checks failed' not in blocked:
        blocked.append('quality checks failed')
    if not targets and changed_files:
        blocked.append('changed files did not map to required quality targets')
    final_status = (
        'PASS'
        if not blocked and (not targets or all(g['status'] == 'PASS' for g in gates))
        else 'BLOCKED'
    )
    payload = {
        'schemaVersion': 1,
        'run_id': identity.raw_run_id,
        'client': identity.client,
        'session_id': identity.raw_session_id,
        'change_id': change_id,
        'created_at': utc_now(),
        'agent_platform': identity.client,
        'subagents': [],
        'changed_files': changed_files,
        'gitEvidence': git_evidence,
        'commits': git_evidence.get('commits', []),
        'committedFiles': git_evidence.get('committedFiles', []),
        'uncommittedFiles': git_evidence.get('uncommittedFiles', []),
        'untrackedFiles': git_evidence.get('untrackedFiles', []),
        'initialDirtySnapshot': git_evidence.get('initialDirtySnapshot', {}),
        'checkoutKind': git_evidence.get('checkoutKind', ''),
        'checkoutCreator': git_evidence.get('checkoutCreator', 'unknown'),
        'targetBranch': git_evidence.get('targetBranch', ''),
        'targetHead': git_evidence.get('targetHead', ''),
        'targetStatus': git_evidence.get('targetStatus', {}),
        'ahead': git_evidence.get('ahead', 0),
        'behind': git_evidence.get('behind', 0),
        'mergeBase': git_evidence.get('mergeBase', ''),
        'primary': git_evidence.get('primary', {}),
        'expected_outcomes': [
            {
                'id': chr(code),
                'required': False,
                'status': 'NOT_RUN',
                'evidence': 'not a runtime-report self-certified outcome',
            }
            for code in range(ord('A'), ord('L') + 1)
        ],
        'effect_checks': [
            {'id': 'git-changed-file-truth', 'status': 'PASS' if not failures else 'FAIL'}
        ],
        'gate_escape_rate': {'status': 'NOT_RUN', 'threshold': 0, 'escape_rate': None},
        'concurrency_matrix': [
            {'id': 'run-scoped-quality', 'status': 'PASS' if not failures else 'BLOCKED'}
        ],
        'gates': gates,
        'skipped_count': 0,
        'blocked_items': blocked,
        'risks': [],
        'notes': ['run-scoped runtime report generated by scripts/harness/stop_entry.py'],
        'status': final_status,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def validate_runtime_report(
    *,
    identity: Any,
    change_id: str,
    repo_root: Path,
    changed_files: list[str],
    report_path: Path,
) -> list[str]:
    """校验 runtime-report。返回 error 列表。"""
    return check_agent_runtime_report.validate_runtime_report(
        run_id=identity.raw_run_id,
        client=identity.client,
        session_id=identity.raw_session_id,
        change_id=change_id,
        worktree_root=repo_root,
        changed_files=changed_files,
        report_path=report_path,
    )
