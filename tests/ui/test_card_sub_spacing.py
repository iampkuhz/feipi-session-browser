"""T030 · card-sub spacing static gate.

Verifies that canonical .card-sub has bottom spacing (margin-bottom or
parent gap) so subtitle text does not collide with the content below it.

Covers P-24 / S-12: card-sub 没有 margin-bottom
"""
from pathlib import Path

import pytest
import re

CSS_PATH = Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "static" / "css" / "ui-primitives.css"


@pytest.fixture(scope="module")
def css_text():
    if not CSS_PATH.exists():
        pytest.skip(f"ui-primitives.css not found at {CSS_PATH}")
    return CSS_PATH.read_text(encoding="utf-8")


def _extract_canonical_card_sub_block(css_text: str) -> str:
    """Extract the canonical .card-sub block (not legacy/migrated ones).

    The canonical definition is the one in the TableToolbar section,
    which does NOT have a comment prefix like 'Originally at style.css'.
    We take the first bare .card-sub { ... } block (not .card .card-sub).
    """
    # Find all .card-sub blocks (not prefixed selectors like .card .card-sub)
    # Pattern: optional comment + .card-sub { ... }
    pattern = r"(?<![\w-])\.card-sub\s*\{([^}]+)\}"
    matches = list(re.finditer(pattern, css_text))
    if not matches:
        return ""
    # The canonical one is the first occurrence that is not inside a migrated block
    # (migrated blocks have "Originally at style.css" comment nearby)
    for m in matches:
        start = max(0, m.start() - 200)
        preceding = css_text[start:m.start()]
        if "Originally at style.css" not in preceding:
            return m.group(1)
    # Fall back to the first match
    return matches[0].group(1)


class TestCardSubSpacing:
    """Canonical .card-sub must have bottom spacing."""

    def test_card_sub_has_margin_bottom_or_parent_gap(self, css_text):
        """The canonical .card-sub block must define margin-bottom,
        or be inside a container with gap (e.g. .table-toolbar with flex gap).

        Acceptable:
        - .card-sub { margin-bottom: ... }
        - .card-sub { margin: ... X Y Z } where bottom value > 0
        - Parent container (e.g. .table-toolbar) has gap that covers spacing
        """
        block = _extract_canonical_card_sub_block(css_text)
        assert block, "No canonical .card-sub block found in ui-primitives.css"

        # Check for explicit margin-bottom
        has_margin_bottom = re.search(r'margin-bottom\s*:', block) is not None

        # Check for shorthand margin with bottom value
        # margin: top right bottom left or margin: vertical horizontal
        margin_shorthand = re.search(r'margin\s*:\s*([^;]+);', block)
        has_margin_shorthand_bottom = False
        if margin_shorthand:
            values = margin_shorthand.group(1).strip().split()
            if len(values) >= 3:
                # 3 or 4 values: third is bottom
                bottom_val = values[2]
                has_margin_shorthand_bottom = bottom_val != "0" and bottom_val != "0px"
            elif len(values) == 2:
                # 2 values: vertical (top=bottom), second is bottom
                bottom_val = values[1]
                has_margin_shorthand_bottom = bottom_val != "0" and bottom_val != "0px"
            elif len(values) == 1:
                bottom_val = values[0]
                has_margin_shorthand_bottom = bottom_val != "0" and bottom_val != "0px"

        # Check that the .table-toolbar parent has gap (flex spacing)
        toolbar_match = re.search(r'\.table-toolbar\s*\{([^}]+)\}', css_text)
        has_parent_gap = False
        if toolbar_match:
            has_parent_gap = re.search(r'gap\s*:\s*[^0]', toolbar_match.group(1)) is not None

        # Either .card-sub itself has bottom margin, or the parent container
        # uses gap, or there's a .section-head / .table-toolbar pattern that
        # provides spacing via its own layout
        assert has_margin_bottom or has_margin_shorthand_bottom or has_parent_gap, (
            f"Canonical .card-sub lacks bottom spacing. "
            f"Block content: '{block.strip()}'. "
            f"margin-bottom: {bool(has_margin_bottom)}, "
            f"margin-shorthand-bottom: {has_margin_shorthand_bottom}, "
            f"parent-gap (.table-toolbar): {has_parent_gap}"
        )

    def test_card_sub_no_zero_margin_bottom(self, css_text):
        """Canonical .card-sub must not explicitly set margin-bottom: 0."""
        block = _extract_canonical_card_sub_block(css_text)
        # It's OK to not have margin-bottom at all; just don't set it to 0
        zero_bottom = re.search(r'margin-bottom\s*:\s*0', block)
        assert zero_bottom is None, (
            f"Canonical .card-sub explicitly sets margin-bottom: 0"
        )
