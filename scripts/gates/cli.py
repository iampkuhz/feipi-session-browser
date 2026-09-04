#!/usr/bin/env python3
"""负责提供 Gate 控制面的唯一公开 CLI；不负责实现各阶段业务逻辑。

命令行入口只编排 ``list``、``explain``、``plan``、``run`` 与 ``health`` 子命令。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gates.catalog import (  # noqa: E402
    CATALOG,
    GATES,
    TARGET_PRESETS,
    ExecutionMode,
    gate_by_name,
    target_preset_by_name,
)
from scripts.gates.evidence import store_run_receipt  # noqa: E402
from scripts.gates.execution import (  # noqa: E402
    ExecutionEvent,
    adapt_recipe_step,
    orchestrate_gate_run,
)
from scripts.gates.maintenance import audit_gate_health  # noqa: E402
from scripts.gates.planning import (  # noqa: E402
    capture_change_snapshot,
    compile_gate_plan,
)
from scripts.gates.presentation import (  # noqa: E402
    render_explanation,
    render_gate_catalog,
    render_gate_plan,
    render_health_audit,
    render_run_receipt,
    render_terminal_event,
)

_FORMATS = ('human', 'json')


def _changed_files(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError('--changed-files must be a JSON array') from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise argparse.ArgumentTypeError('--changed-files must be a JSON string array')
    return tuple(parsed)


def _selection_arguments(parser: argparse.ArgumentParser) -> None:
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument('--gate', choices=tuple(gate.name for gate in GATES))
    selector.add_argument('--target', choices=tuple(item.name for item in TARGET_PRESETS))


def _plan_arguments(parser: argparse.ArgumentParser, *, include_format: bool) -> None:
    parser.add_argument('--mode', required=True, choices=tuple(ExecutionMode))
    _selection_arguments(parser)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--base')
    source.add_argument('--changed-files', type=_changed_files)
    parser.add_argument('--base-url')
    if include_format:
        parser.add_argument('--format', choices=_FORMATS, default='human')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Explicit structured Gate control plane')
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='List Gate and TargetPreset declarations')
    listing.add_argument('--format', choices=_FORMATS, default='human')
    explain = commands.add_parser('explain', help='Explain one Gate or TargetPreset')
    _selection_arguments(explain)
    explain.add_argument('--format', choices=_FORMATS, default='human')
    _plan_arguments(
        commands.add_parser('plan', help='Compile without executing'), include_format=True
    )
    _plan_arguments(
        commands.add_parser('run', help='Compile, execute, and store receipt'), include_format=False
    )
    health = commands.add_parser('health', help='Check Gate control-plane health')
    health.add_argument('--format', choices=_FORMATS, default='human')
    return parser


def _event_sink(event: ExecutionEvent) -> None:
    values = asdict(event)
    kind = str(values.pop('kind'))
    print(render_terminal_event(kind, values), file=sys.stderr, flush=True)


def _compile(args: argparse.Namespace, repo_root: Path):
    snapshot = capture_change_snapshot(
        repo_root,
        mode=args.mode,
        base=args.base,
        changed_files=args.changed_files,
    )

    def invocation_factory(gate, recipe_step):
        """把当前 CLI 参数绑定到一个 RecipeStep 的冻结命令适配过程。"""
        return adapt_recipe_step(
            gate,
            recipe_step,
            repo_root,
            mode=args.mode,
            changed_files=snapshot.files,
            base_url=args.base_url or os.environ.get('BASE_URL'),
        )

    return compile_gate_plan(
        snapshot,
        mode=args.mode,
        target=args.target,
        gate=args.gate,
        invocation_factory=invocation_factory,
    )


def _explain(args: argparse.Namespace) -> str:
    if args.gate:
        subject = gate_by_name(args.gate)
    elif args.target:
        subject = target_preset_by_name(args.target)
    else:
        raise ValueError('explain requires exactly one of --gate or --target')
    return render_explanation(subject, CATALOG, output_format=args.format)


def _run(args: argparse.Namespace, repo_root: Path) -> int:
    started_at = datetime.now(UTC).isoformat()
    plan = _compile(args, repo_root)
    results = orchestrate_gate_run(plan, repo_root, event_sink=_event_sink)
    finished_at = datetime.now(UTC).isoformat()
    receipt = store_run_receipt(
        plan,
        results,
        repo_root=repo_root,
        reason='input-empty' if not plan.gates else '',
        started_at=started_at,
        finished_at=finished_at,
    )
    print(render_run_receipt(receipt))
    return {'PASS': 0, 'BLOCKED': 1}.get(receipt.status, 2)


def _health(args: argparse.Namespace, repo_root: Path) -> int:
    audit = audit_gate_health(repo_root=repo_root, event_sink=_event_sink)
    print(render_health_audit(audit, output_format=args.format))
    return {'PASS': 0, 'BLOCKED': 1}.get(str(audit.status), 2)


def main(argv: list[str] | None = None) -> int:
    """解析明确子命令；输入、环境或执行不可用时返回 FAIL。"""

    try:
        args = _parser().parse_args(argv)
        repo_root = Path.cwd().resolve()
        if args.command == 'list':
            print(render_gate_catalog(CATALOG, output_format=args.format))
            return 0
        if args.command == 'explain':
            print(_explain(args))
            return 0
        if args.command == 'plan':
            print(render_gate_plan(_compile(args, repo_root), output_format=args.format))
            return 0
        if args.command == 'run':
            return _run(args, repo_root)
        return _health(args, repo_root)
    except KeyboardInterrupt:
        print('DONE status=FAIL reason=interrupted', file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            f'DONE status=FAIL reason=input-or-runtime-unavailable detail={type(exc).__name__}:{exc}',
            file=sys.stderr,
        )
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
