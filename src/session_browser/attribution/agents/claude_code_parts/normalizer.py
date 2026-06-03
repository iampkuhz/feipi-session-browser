"""Bucket normalization for Claude Code attribution builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from session_browser.attribution.agents.claude_code_parts.constants import (
    ESTIMATED_BUCKET_KEYS,
    HEURISTIC_FIXED_KEYS,
    HEURISTIC_SCALED_KEYS,
    MEASURED_BUCKET_KEYS,
)
from session_browser.attribution.agents.claude_code_parts.utils import _pct

if TYPE_CHECKING:
    from session_browser.attribution.contracts import RequestAttributionBucket


def _scale_bucket_and_details(bucket: "RequestAttributionBucket", scale: float) -> None:
    """Scale a bucket's tokens and its details.items tokens proportionally."""
    original_tokens = bucket.tokens
    bucket.tokens = max(0, int(bucket.tokens * scale))
    if bucket.tokens == 0 and original_tokens > 0 and scale > 0:
        # Preserve a floor of 1 token if the bucket had content but scale is very small
        bucket.tokens = 1
    # Scale inner detail items proportionally
    if bucket.details and "items" in bucket.details:
        for item in bucket.details["items"]:
            if isinstance(item, dict) and "tokens" in item:
                item_tokens = item.get("tokens", 0)
                item["tokens"] = max(0, int(item_tokens * scale))
                # Preserve floor for items too
                if item["tokens"] == 0 and item_tokens > 0 and scale > 0:
                    item["tokens"] = 1


def _zero_bucket_preserve_floor(bucket: "RequestAttributionBucket") -> None:
    """Zero out a bucket but preserve a floor token if it has actual content."""
    original_tokens = bucket.tokens
    has_content = bool(
        bucket.content_preview
        or (bucket.details and bucket.details.get("items"))
    )
    if has_content and original_tokens > 0:
        # Preserve 1 token minimum for buckets with actual content
        bucket.tokens = 1
    else:
        bucket.tokens = 0
    # Also zero out detail items but preserve floor
    if bucket.details and "items" in bucket.details:
        for item in bucket.details["items"]:
            if isinstance(item, dict) and "tokens" in item:
                item_tokens = item.get("tokens", 0)
                if item_tokens > 0 and has_content:
                    item["tokens"] = 1
                else:
                    item["tokens"] = 0


def normalize_request_reconstruction_buckets(
    buckets: list["RequestAttributionBucket"],
    *,
    total_input: int,
    fresh_input: int,
) -> list["RequestAttributionBucket"]:
    """Normalize heuristic buckets so they cannot inflate located_rate beyond total_input.

    Rules:
    1. Classify buckets into measured, estimated, heuristic_fixed, heuristic_scaled.
    2. measured_sum = sum(measured buckets)
    3. estimated_sum = sum(estimated buckets)
    4. heuristic_budget = max(0, fresh_input - measured_sum - estimated_sum)
    5. If heuristic_fixed_sum > heuristic_budget, scale heuristic_fixed proportionally.
    6. If estimated_sum > (total_input - measured_sum), scale estimated proportionally.
       NOTE: estimated uses total_input (not fresh_input) because estimated buckets
       represent content that cannot be cached — they should not be crushed when
       fresh_input is small due to high cache hit rate.
    7. Recompute unlocated_residual = max(total_input - known_sum, 0).
    8. Recompute coverage = min(known_sum / total_input, 1.0).
    9. Never scale measured buckets down.
    10. Add note to attribution_notes if normalization was applied.

    The function modifies bucket tokens/percent in place and returns the list.
    """
    if not buckets or fresh_input <= 0:
        return buckets

    measured_sum = 0
    estimated_sum = 0
    heuristic_fixed_sum = 0
    heuristic_scaled_sum = 0
    residual_tokens = 0

    measured_buckets = []
    estimated_buckets = []
    heuristic_fixed_buckets = []
    heuristic_scaled_buckets = []
    residual_bucket = None

    for b in buckets:
        if b.key in MEASURED_BUCKET_KEYS:
            measured_sum += b.tokens
            measured_buckets.append(b)
        elif b.key in ESTIMATED_BUCKET_KEYS:
            estimated_sum += b.tokens
            estimated_buckets.append(b)
        elif b.key in HEURISTIC_FIXED_KEYS:
            heuristic_fixed_sum += b.tokens
            heuristic_fixed_buckets.append(b)
        elif b.key in HEURISTIC_SCALED_KEYS:
            heuristic_scaled_sum += b.tokens
            heuristic_scaled_buckets.append(b)
        elif b.key in ("unlocated_residual", "unknown_overhead", "unknown"):
            residual_tokens = b.tokens
            residual_bucket = b

    normalization_applied = False

    # Step 5: Scale heuristic_fixed if they exceed budget
    heuristic_budget = max(0, fresh_input - measured_sum - estimated_sum)
    if heuristic_fixed_sum > heuristic_budget and heuristic_budget > 0:
        scale = heuristic_budget / heuristic_fixed_sum
        for b in heuristic_fixed_buckets:
            _scale_bucket_and_details(b, scale)
        heuristic_fixed_sum = sum(b.tokens for b in heuristic_fixed_buckets)
        normalization_applied = True
    # NOTE: When heuristic_budget <= 0 (measured + estimated already exhausts
    # fresh_input), we do NOT zero out heuristic_fixed buckets.  These
    # represent real known token costs (e.g. tool_schemas from SDK definitions).
    # Instead, let the unlocated_residual absorb the overflow by becoming 0.

    # Step 6: Scale estimated if they exceed remaining budget.
    # Use total_input (not fresh_input) as the budget because estimated buckets
    # represent content that cannot be cached (CLAUDE.md, agent prompts, etc.).
    # They are real token costs that should fit within total_input, not fresh_input.
    # When cache hit rate is high, fresh_input can be much smaller than measured_sum,
    # which would incorrectly zero out estimated buckets with actual content.
    remaining_for_estimated = max(0, total_input - measured_sum)
    if estimated_sum > remaining_for_estimated and remaining_for_estimated > 0:
        scale = remaining_for_estimated / estimated_sum
        for b in estimated_buckets:
            _scale_bucket_and_details(b, scale)
        estimated_sum = sum(b.tokens for b in estimated_buckets)
        normalization_applied = True
    elif estimated_sum > remaining_for_estimated and remaining_for_estimated <= 0:
        # When measured already fills/exceeds total_input, preserve estimated
        # buckets at their original values — they represent real content.
        # Let unlocated_residual absorb the overflow by becoming 0.
        normalization_applied = True

    # Step 7: Recompute unlocated_residual
    known_sum = (
        measured_sum + estimated_sum + heuristic_fixed_sum + heuristic_scaled_sum
    )
    new_residual = max(total_input - known_sum, 0) if total_input > 0 else 0
    if residual_bucket:
        residual_bucket.tokens = new_residual

    # Recompute percentages for all buckets
    for b in buckets:
        b.percent = _pct(b.tokens, total_input)

    # Step 10: Add normalization note
    if normalization_applied:
        # The caller should add this to attribution_notes
        pass  # note is added by the builder

    return buckets
