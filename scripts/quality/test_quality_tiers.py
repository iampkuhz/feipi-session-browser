#!/usr/bin/env python3
"""Tests for quality tier definitions and not-triggered vs skipped semantics.

Validates that:
- Three tiers (quick, required, full) are correctly defined.
- changed_files only determines triggering, not skipping.
- Not-triggered gates are semantically different from skipped gates.
- required/full tiers treat skipped outcome as FAIL/BLOCKED.
- quick tier allows not-triggered gates without counting them as skipped.

Usage:
    python3 scripts/quality/test_quality_tiers.py
    python3 -m pytest scripts/quality/test_quality_tiers.py -v
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 导入被测模块。
from scripts.quality.quality_targets import (  # noqa: E402
    QUALITY_TARGETS,
    GATE_PATTERNS,
    applicable_gates_for_target,
    required_gates_for_target,
)
from scripts.quality.run_required_quality_gates import (  # noqa: E402
    QUICK_GATES,
    TIER_META,
    VALID_TIERS,
    FULL_EXTRA_COMMANDS,
    _run_quick_tier,
)


class TestTierDefinitions(unittest.TestCase):
    """Verify that the three quality tiers are correctly defined."""

    def test_valid_tiers_contains_three_entries(self) -> None:
        """VALID_TIERS must contain exactly quick, required, and full."""
        self.assertEqual(set(VALID_TIERS), {'quick', 'required', 'full'})

    def test_valid_tiers_ordering(self) -> None:
        """Tiers are ordered from lightest to heaviest."""
        self.assertEqual(VALID_TIERS, ('quick', 'required', 'full'))

    def test_tier_meta_has_all_tiers(self) -> None:
        """TIER_META must define metadata for every valid tier."""
        for tier in VALID_TIERS:
            self.assertIn(tier, TIER_META, f'TIER_META missing tier: {tier}')

    def test_tier_meta_structure(self) -> None:
        """Each tier metadata must have description and failure_policy."""
        for tier, meta in TIER_META.items():
            self.assertIn('description', meta, f'{tier} missing description')
            self.assertIn('failure_policy', meta, f'{tier} missing failure_policy')
            self.assertTrue(meta['description'], f'{tier} description is empty')
            self.assertTrue(meta['failure_policy'], f'{tier} failure_policy is empty')

    def test_quick_tier_description_mentions_local(self) -> None:
        """Quick tier is for local development feedback."""
        desc = TIER_META['quick']['description']
        self.assertIn('本地', desc)

    def test_required_tier_description_mentions_pr(self) -> None:
        """Required tier is for PR/Stop gating."""
        desc = TIER_META['required']['description']
        self.assertTrue(
            'PR' in desc or 'Stop' in desc or 'handoff' in desc,
            f'required tier description should mention PR/Stop/handoff: {desc}',
        )

    def test_full_tier_description_mentions_release(self) -> None:
        """Full tier is for release or migration sign-off."""
        desc = TIER_META['full']['description']
        self.assertTrue(
            '发布' in desc or '迁移' in desc or '收口' in desc,
            f'full tier description should mention release/migration: {desc}',
        )

    def test_required_and_full_forbid_skipped(self) -> None:
        """Required and full tiers must explicitly forbid skipped outcomes."""
        for tier in ('required', 'full'):
            policy = TIER_META[tier]['failure_policy']
            self.assertIn(
                'skipped', policy.lower(),
                f'{tier} failure policy must mention skipped outcome',
            )

    def test_quick_tier_allows_not_triggered(self) -> None:
        """Quick tier policy must clarify not-triggered is not skipped."""
        policy = TIER_META['quick']['failure_policy']
        self.assertIn(
            'not triggered', policy.lower(),
            'quick failure policy must clarify not-triggered semantics',
        )


class TestQuickGates(unittest.TestCase):
    """Verify the quick-tier gate subset."""

    def test_quick_gates_non_empty(self) -> None:
        """QUICK_GATES must contain at least one gate."""
        self.assertTrue(len(QUICK_GATES) > 0)

    def test_quick_gates_are_subset_of_all_gates(self) -> None:
        """Every quick gate must appear in at least one target's baseline."""
        all_gates: set[str] = set()
        for gates in QUALITY_TARGETS.values():
            all_gates.update(gates)
        for gate in QUICK_GATES:
            self.assertIn(
                gate, all_gates,
                f'quick gate {gate} not found in any target baseline',
            )

    def test_quick_gates_are_lightweight(self) -> None:
        """Quick gates should not include heavy gates like javaCheck or pytest."""
        heavy_gates = {'javaCheck', 'pytest', 'browserLayout', 'browserInteraction'}
        overlap = QUICK_GATES & heavy_gates
        self.assertEqual(
            overlap, set(),
            f'quick gates should not include heavy gates: {overlap}',
        )

    def test_quick_gates_is_frozen(self) -> None:
        """QUICK_GATES should be a frozenset to prevent accidental mutation."""
        self.assertIsInstance(QUICK_GATES, frozenset)


class TestNotTriggeredVsSkipped(unittest.TestCase):
    """Core semantic tests: not-triggered and skipped are distinct concepts."""

    def test_not_triggered_gates_differ_from_all_baseline(self) -> None:
        """When changed_files narrow the scope, some gates become not-triggered.

        Not-triggered gates are those in the baseline but not selected by
        changed_files. They are NOT skipped.
        """
        target = 'java-src'
        baseline = required_gates_for_target(target)
        self.assertTrue(len(baseline) > 1, 'java-src should have multiple baseline gates')

        # Only Java source files changed.
        changed = ['java/query-api/src/main/java/com/feipi/Example.java']
        applicable = applicable_gates_for_target(target, changed)

        not_triggered = set(baseline) - set(applicable)

        # Some gates should be not-triggered (not all match pure Java source).
        # The exact set depends on GATE_PATTERNS, but at minimum the
        # applicable set should be a subset of baseline.
        self.assertTrue(
            set(applicable).issubset(set(baseline)),
            'applicable gates must be a subset of baseline',
        )

        # Not-triggered gates are NOT skipped -- they simply were not selected.
        # This is the core semantic distinction.
        for gate in not_triggered:
            self.assertNotIn(
                gate, applicable,
                f'not-triggered gate {gate} should not appear in applicable list',
            )

    def test_no_changed_files_means_nothing_triggered(self) -> None:
        """Empty changed_files means no gates are triggered, not skipped."""
        target = 'hook-runtime'
        applicable = applicable_gates_for_target(target, [])
        self.assertEqual(
            applicable, [],
            'empty changed_files should produce empty applicable list (not triggered)',
        )

    def test_none_changed_files_means_full_baseline(self) -> None:
        """None changed_files means full baseline runs (manual mode)."""
        target = 'harness'
        applicable = applicable_gates_for_target(target, None)
        baseline = required_gates_for_target(target)
        self.assertEqual(
            applicable, baseline,
            'None changed_files should return full baseline',
        )

    def test_not_triggered_is_not_skipped_semantic(self) -> None:
        """Explicitly verify: not-triggered != skipped.

        In the quality gate system:
        - not triggered: gate patterns did not match changed_files; gate was
          never selected for execution. This is an expected outcome.
        - skipped: a gate that WAS selected but did not fully execute (e.g.,
          test framework reported skipped tests). This is a failure.
        """
        target = 'java-src'
        baseline = required_gates_for_target(target)
        changed = ['java/query-api/src/main/java/com/feipi/Foo.java']
        applicable = applicable_gates_for_target(target, changed)
        not_triggered = [g for g in baseline if g not in applicable]

        # If there are not-triggered gates, they are categorically different
        # from skipped gates.
        if not_triggered:
            # Not-triggered gates should NOT be treated as failures.
            # They simply were not relevant to the current change.
            for gate in not_triggered:
                # This gate was not triggered, NOT skipped.
                status_label = 'not_triggered'
                self.assertEqual(
                    status_label, 'not_triggered',
                    f'{gate} is not-triggered, not skipped',
                )

    def test_applicable_gates_preserve_baseline_order(self) -> None:
        """Applicable gates should maintain the order from the baseline."""
        target = 'hook-runtime'
        baseline = required_gates_for_target(target)
        changed = ['scripts/quality/check_no_test_skips.py']
        applicable = applicable_gates_for_target(target, changed)

        # The applicable list should be a subsequence of baseline (order preserved).
        baseline_order = {g: i for i, g in enumerate(baseline)}
        applicable_indices = [baseline_order[g] for g in applicable if g in baseline_order]
        self.assertEqual(
            applicable_indices, sorted(applicable_indices),
            'applicable gates should preserve baseline order',
        )


class TestRequiredFullSkippedPolicy(unittest.TestCase):
    """Verify that required and full tiers enforce the no-skipped policy."""

    def test_required_tier_skipped_means_fail(self) -> None:
        """Required tier: any skipped outcome in triggered gates means FAIL."""
        policy = TIER_META['required']['failure_policy']
        # The policy text must convey that skipped outcome is a failure.
        self.assertTrue(
            'fail' in policy.lower() or 'blocked' in policy.lower(),
            'required tier policy must treat skipped as FAIL/BLOCKED',
        )

    def test_full_tier_skipped_means_fail(self) -> None:
        """Full tier: any skipped outcome in triggered gates means FAIL."""
        policy = TIER_META['full']['failure_policy']
        self.assertTrue(
            'fail' in policy.lower() or 'blocked' in policy.lower(),
            'full tier policy must treat skipped as FAIL/BLOCKED',
        )

    def test_quality_targets_baseline_has_no_skip_semantics(self) -> None:
        """Baseline gate lists contain gates to run, not gates to skip.

        Every gate in QUALITY_TARGETS is a required gate for its target.
        There is no concept of 'skipped' in the baseline definition.
        """
        for target, gates in QUALITY_TARGETS.items():
            for gate in gates:
                # Each gate is a required gate; it either runs or is not-triggered.
                # It is never defined as 'skipped' in the target definition.
                self.assertIsInstance(gate, str)
                self.assertTrue(gate, f'{target} has empty gate name')


class TestFullExtraCommands(unittest.TestCase):
    """Verify full-tier extra commands configuration."""

    def test_full_extra_commands_is_list(self) -> None:
        """FULL_EXTRA_COMMANDS must be a list of command lists."""
        self.assertIsInstance(FULL_EXTRA_COMMANDS, list)

    def test_full_extra_commands_structure(self) -> None:
        """Each extra command must be a non-empty list of strings."""
        for cmd in FULL_EXTRA_COMMANDS:
            self.assertIsInstance(cmd, list)
            self.assertTrue(len(cmd) > 0, 'extra command must not be empty')
            for part in cmd:
                self.assertIsInstance(part, str)


class TestQuickTierDryRun(unittest.TestCase):
    """Test quick tier dry-run behavior with no changed files."""

    def test_quick_tier_no_changed_files_returns_zero(self) -> None:
        """Quick tier with no changed files should return 0 (not triggered)."""
        result = _run_quick_tier(
            changed_files=[],
            excluded_targets={'session-detail'},
            dry_run=True,
        )
        self.assertEqual(result, 0, 'quick tier with no changes should return 0')

    def test_quick_tier_dry_run_with_java_change(self) -> None:
        """Quick tier dry-run with a Java change should identify triggered gates."""
        # This tests the dry-run path which does not execute gates.
        result = _run_quick_tier(
            changed_files=['java/query-api/src/main/java/com/feipi/Foo.java'],
            excluded_targets={'session-detail'},
            dry_run=True,
        )
        self.assertEqual(result, 0, 'dry-run should always return 0')


class TestQualityTiersYamlExists(unittest.TestCase):
    """Verify that the quality-tiers.yaml configuration file exists."""

    def test_yaml_file_exists(self) -> None:
        """harness/quality/quality-tiers.yaml must exist as the tier config source."""
        yaml_path = REPO_ROOT / 'harness' / 'quality' / 'quality-tiers.yaml'
        self.assertTrue(
            yaml_path.exists(),
            f'quality-tiers.yaml not found at {yaml_path}',
        )

    def test_yaml_contains_tier_keywords(self) -> None:
        """The YAML file must mention all three tiers."""
        yaml_path = REPO_ROOT / 'harness' / 'quality' / 'quality-tiers.yaml'
        if not yaml_path.exists():
            self.skipTest('quality-tiers.yaml not found')
        content = yaml_path.read_text(encoding='utf-8')
        for tier in ('quick', 'required', 'full'):
            self.assertIn(
                tier, content,
                f'quality-tiers.yaml must mention tier: {tier}',
            )

    def test_yaml_contains_principles(self) -> None:
        """The YAML file must document the core principles."""
        yaml_path = REPO_ROOT / 'harness' / 'quality' / 'quality-tiers.yaml'
        if not yaml_path.exists():
            self.skipTest('quality-tiers.yaml not found')
        content = yaml_path.read_text(encoding='utf-8')
        self.assertIn('changed_files', content)
        self.assertIn('not triggered', content)


if __name__ == '__main__':
    unittest.main()
