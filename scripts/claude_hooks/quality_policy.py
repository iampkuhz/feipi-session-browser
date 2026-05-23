"""兼容入口：实际实现位于 scripts.claude_hooks.policy.quality_policy。"""

from .policy.quality_policy import command_for_target, infer_required_targets

__all__ = ["command_for_target", "infer_required_targets"]
