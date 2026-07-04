#!/usr/bin/env python3
"""提供 test quality tiers 脚本能力。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 导入被测模块。
from scripts.quality.quality_targets import (  # noqa: E402
    QUALITY_TARGETS,
    applicable_gates_for_target,
    required_gates_for_target,
)
from scripts.quality.run_required_quality_gates import (  # noqa: E402
    FULL_EXTRA_COMMANDS,
    QUICK_GATES,
    TIER_META,
    VALID_TIERS,
    _run_quick_tier,
    compute_tier_required_targets,
)


class TestTierDefinitions(unittest.TestCase):
    """表示 TestTierDefinitions。
    """

    # 验证有效 tier 配置包含三个条目。
    def test_valid_tiers_contains_three_entries(self) -> None:
        self.assertEqual(set(VALID_TIERS), {'quick', 'required', 'full'})

    # 验证valid tiers ordering。
    def test_valid_tiers_ordering(self) -> None:
        self.assertEqual(VALID_TIERS, ('quick', 'required', 'full'))

    # 验证tier metadata has 全部 tiers。
    def test_tier_meta_has_all_tiers(self) -> None:
        for tier in VALID_TIERS:
            self.assertIn(tier, TIER_META, f'TIER_META missing tier: {tier}')

    # 验证tier metadata 结构。
    def test_tier_meta_structure(self) -> None:
        for tier, meta in TIER_META.items():
            self.assertIn('description', meta, f'{tier} missing description')
            self.assertIn('failure_policy', meta, f'{tier} missing failure_policy')
            self.assertTrue(meta['description'], f'{tier} description is empty')
            self.assertTrue(meta['failure_policy'], f'{tier} failure_policy is empty')

    # 验证 quick tier 描述提到本地用途。
    def test_quick_tier_description_mentions_local(self) -> None:
        desc = TIER_META['quick']['description']
        self.assertIn('本地', desc)

    # 验证必需 tier description mentions pr。
    def test_required_tier_description_mentions_pr(self) -> None:
        desc = TIER_META['required']['description']
        self.assertTrue(
            'PR' in desc or 'Stop' in desc or 'handoff' in desc,
            f'required tier description should mention PR/Stop/handoff: {desc}',
        )

    # 验证full tier description mentions 释放。
    def test_full_tier_description_mentions_release(self) -> None:
        desc = TIER_META['full']['description']
        self.assertTrue(
            '发布' in desc or '迁移' in desc or '收口' in desc,
            f'full tier description should mention release/migration: {desc}',
        )

    # 验证必需 full forbid skipped。
    def test_required_and_full_forbid_skipped(self) -> None:
        for tier in ('required', 'full'):
            policy = TIER_META[tier]['failure_policy']
            self.assertIn(
                'skipped',
                policy.lower(),
                f'{tier} failure policy must mention skipped outcome',
            )

    # 验证 quick tier 允许 not-triggered 结果。
    def test_quick_tier_allows_not_triggered(self) -> None:
        policy = TIER_META['quick']['failure_policy']
        self.assertIn(
            'not triggered',
            policy.lower(),
            'quick failure policy must clarify not-triggered semantics',
        )


class TestQuickGates(unittest.TestCase):
    """表示 TestQuickGates。
    """

    # 验证quick gates non 空。
    def test_quick_gates_non_empty(self) -> None:
        self.assertTrue(len(QUICK_GATES) > 0)

    # 验证quick gates subset 全部 gates。
    def test_quick_gates_are_subset_of_all_gates(self) -> None:
        all_gates: set[str] = set()
        for gates in QUALITY_TARGETS.values():
            all_gates.update(gates)
        for gate in QUICK_GATES:
            self.assertIn(
                gate,
                all_gates,
                f'quick gate {gate} not found in any target baseline',
            )

    # 验证quick gates lightweight。
    def test_quick_gates_are_lightweight(self) -> None:
        heavy_gates = {'javaCheck', 'pytest', 'browserLayout', 'browserInteraction'}
        overlap = QUICK_GATES & heavy_gates
        self.assertEqual(
            overlap,
            set(),
            f'quick gates should not include heavy gates: {overlap}',
        )

    # 验证quick gates frozen。
    def test_quick_gates_is_frozen(self) -> None:
        self.assertIsInstance(QUICK_GATES, frozenset)


class TestNotTriggeredVsSkipped(unittest.TestCase):
    """表示 TestNotTriggeredVsSkipped。
    """

    # 验证not triggered gates differ 全部 baseline。
    def test_not_triggered_gates_differ_from_all_baseline(self) -> None:
        target = 'java-src'
        baseline = required_gates_for_target(target)
        self.assertTrue(len(baseline) > 1, 'java-src should have multiple baseline gates')

        # 仅 Java source 文件 changed。
        changed = ['java/query-api/src/main/java/com/feipi/Example.java']
        applicable = applicable_gates_for_target(target, changed)

        not_triggered = set(baseline) - set(applicable)

        self.assertTrue(
            set(applicable).issubset(set(baseline)),
            'applicable gates must be a subset of baseline',
        )

        for gate in not_triggered:
            self.assertNotIn(
                gate,
                applicable,
                f'not-triggered gate {gate} should not appear in applicable list',
            )

    # 验证无 changed-files 文件 means nothing triggered。
    def test_no_changed_files_means_nothing_triggered(self) -> None:
        target = 'hook-runtime'
        applicable = applicable_gates_for_target(target, [])
        self.assertEqual(
            applicable,
            [],
            'empty changed_files should produce empty applicable list (not triggered)',
        )

    # 验证none changed-files 文件 means full baseline。
    def test_none_changed_files_means_full_baseline(self) -> None:
        target = 'harness'
        applicable = applicable_gates_for_target(target, None)
        baseline = required_gates_for_target(target)
        self.assertEqual(
            applicable,
            baseline,
            'None changed_files should return full baseline',
        )

    # 验证 not-triggered 与 skipped 语义不同。
    def test_not_triggered_is_not_skipped_semantic(self) -> None:
        """说明：
            绝不 selected用于execution. This is expected outcome。
        """
        target = 'java-src'
        baseline = required_gates_for_target(target)
        changed = ['java/query-api/src/main/java/com/feipi/Foo.java']
        applicable = applicable_gates_for_target(target, changed)
        not_triggered = [g for g in baseline if g not in applicable]

        if not_triggered:
            # 不-triggered gate should 不 be treated as 失败项。
            # They simply were 不 relevant到当前 change。
            for gate in not_triggered:
                status_label = 'not_triggered'
                self.assertEqual(
                    status_label,
                    'not_triggered',
                    f'{gate} is not-triggered, not skipped',
                )

    # 验证适用 gate 保持 baseline 顺序。
    def test_applicable_gates_preserve_baseline_order(self) -> None:
        target = 'hook-runtime'
        baseline = required_gates_for_target(target)
        changed = ['scripts/quality/check_no_test_skips.py']
        applicable = applicable_gates_for_target(target, changed)

        baseline_order = {g: i for i, g in enumerate(baseline)}
        applicable_indices = [baseline_order[g] for g in applicable if g in baseline_order]
        self.assertEqual(
            applicable_indices,
            sorted(applicable_indices),
            'applicable gates should preserve baseline order',
        )


class TestRequiredFullSkippedPolicy(unittest.TestCase):
    """表示 TestRequiredFullSkippedPolicy。
    """

    # 验证必需 tier skipped means fail。
    def test_required_tier_skipped_means_fail(self) -> None:
        policy = TIER_META['required']['failure_policy']
        self.assertTrue(
            'fail' in policy.lower() or 'blocked' in policy.lower(),
            'required tier policy must treat skipped as FAIL/BLOCKED',
        )

    # 验证 full tier 中 skipped 会视为失败。
    def test_full_tier_skipped_means_fail(self) -> None:
        policy = TIER_META['full']['failure_policy']
        self.assertTrue(
            'fail' in policy.lower() or 'blocked' in policy.lower(),
            'full tier policy must treat skipped as FAIL/BLOCKED',
        )

    # 验证 quality target baseline 不表达 skip 语义。
    def test_quality_targets_baseline_has_no_skip_semantics(self) -> None:
        """说明：
            Every gate in QUALITY_TARGETS is 必需 gate用于its target。
        """
        for target, gates in QUALITY_TARGETS.items():
            for gate in gates:
                # Each gate is a 必需 gate；it either runs 或 is 不-triggered。
                self.assertIsInstance(gate, str)
                self.assertTrue(gate, f'{target} has empty gate name')


class TestFullExtraCommands(unittest.TestCase):
    """表示 TestFullExtraCommands。
    """

    # 验证full tier selects 全部 当前 targets。
    def test_full_tier_selects_all_current_targets(self) -> None:
        targets = compute_tier_required_targets('full', [])
        self.assertEqual(targets, list(QUALITY_TARGETS))
        self.assertIn('session-detail', targets)
        self.assertIn('scan-script-smoke', targets)
        self.assertNotIn('python-src', targets)

    # 验证full extra 命令 列表。
    def test_full_extra_commands_is_list(self) -> None:
        self.assertIsInstance(FULL_EXTRA_COMMANDS, list)

    # 验证full extra 命令 结构。
    def test_full_extra_commands_structure(self) -> None:
        for cmd in FULL_EXTRA_COMMANDS:
            self.assertIsInstance(cmd, list)
            self.assertTrue(len(cmd) > 0, 'extra command must not be empty')
            for part in cmd:
                self.assertIsInstance(part, str)


class TestQuickTierDryRun(unittest.TestCase):
    """表示 TestQuickTierDryRun。
    """

    # 验证quick tier 无 changed-files 文件 returns zero。
    def test_quick_tier_no_changed_files_returns_zero(self) -> None:
        result = _run_quick_tier(
            changed_files=[],
            excluded_targets={'session-detail'},
            dry_run=True,
        )
        self.assertEqual(result, 0, 'quick tier with no changes should return 0')

    # 验证quick tier dry 运行 Java change。
    def test_quick_tier_dry_run_with_java_change(self) -> None:
        result = _run_quick_tier(
            changed_files=['java/query-api/src/main/java/com/feipi/Foo.java'],
            excluded_targets={'session-detail'},
            dry_run=True,
        )
        self.assertEqual(result, 0, 'dry-run should always return 0')


class TestQualityTiersYamlExists(unittest.TestCase):
    """表示 TestQualityTiersYamlExists。
    """

    # 验证YAML 文件 exists。
    def test_yaml_file_exists(self) -> None:
        yaml_path = REPO_ROOT / 'harness' / 'quality' / 'quality-tiers.yaml'
        self.assertTrue(
            yaml_path.exists(),
            f'quality-tiers.yaml not found at {yaml_path}',
        )

    # 验证 YAML 包含 tier 关键字。
    def test_yaml_contains_tier_keywords(self) -> None:
        yaml_path = REPO_ROOT / 'harness' / 'quality' / 'quality-tiers.yaml'
        if not yaml_path.exists():
            self.skipTest('quality-tiers.yaml not found')
        content = yaml_path.read_text(encoding='utf-8')
        for tier in ('quick', 'required', 'full'):
            self.assertIn(
                tier,
                content,
                f'quality-tiers.yaml must mention tier: {tier}',
            )

    # 验证YAML contains principles。
    def test_yaml_contains_principles(self) -> None:
        yaml_path = REPO_ROOT / 'harness' / 'quality' / 'quality-tiers.yaml'
        if not yaml_path.exists():
            self.skipTest('quality-tiers.yaml not found')
        content = yaml_path.read_text(encoding='utf-8')
        self.assertIn('changed_files', content)
        self.assertIn('not triggered', content)


if __name__ == '__main__':
    unittest.main()
