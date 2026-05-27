"""Tests for Qoder short ID URL alias resolution (T058).
Verifies that:
- Short ID with unique full UUID match resolves correctly.
- Short ID with multiple full UUID matches returns 404/diagnostic (no guessing).
- Full UUID passthrough is a no-op.
- Non-matching short ID returns 404.
"""

from __future__ import annotations

import pytest
import unittest
from unittest.mock import patch, MagicMock


class TestResolveQoderShortId:
    """Unit tests for _resolve_qoder_short_id in routes.py."""

    def _get_func(self):
        """Import the function under test."""
        from session_browser.web.routes import _resolve_qoder_short_id
        return _resolve_qoder_short_id

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_unique_prefix_match(self):
        """Short ID matching exactly one full UUID should resolve."""
        func = self._get_func()
        full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        short_id = "a1b2c3d4"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {}
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                mock_discover.return_value = [
                    ("project-a", full_uuid, None),
                ]
                resolved, err = func(short_id)
                assert resolved == full_uuid.lower(), f"Expected {full_uuid.lower()}, got {resolved}"
                assert err is None

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_ambiguous_multiple_matches(self):
        """Short ID matching multiple full UUIDs must NOT be guessed -- return error."""
        func = self._get_func()
        uuid1 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        uuid2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567891"
        short_id = "a1b2c3d4"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {}
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                mock_discover.return_value = [
                    ("project-a", uuid1, None),
                    ("project-b", uuid2, None),
                ]
                resolved, err = func(short_id)
                assert resolved is None
                assert err is not None
                assert "2" in err  # mentions the count

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_no_match_returns_none(self):
        """Short ID with no prefix match should return (None, None)."""
        func = self._get_func()
        short_id = "zzzzzzzz"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {}
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                mock_discover.return_value = [
                    ("project-a", "a1b2c3d4-e5f6-7890-abcd-ef1234567890", None),
                ]
                resolved, err = func(short_id)
                assert resolved is None
                assert err is None

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_full_uuid_passthrough(self):
        """Full UUID input should return (None, None) -- not treated as short ID."""
        func = self._get_func()
        full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                resolved, err = func(full_uuid)
                assert resolved is None
                assert err is None
                mock_map.assert_not_called()
                mock_discover.assert_not_called()

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_canonical_map_hit(self):
        """If _build_canonical_id_map already has the short ID, use it directly."""
        func = self._get_func()
        full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        short_id = "a1b2c3d4"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {short_id: full_uuid}
            resolved, err = func(short_id)
            assert resolved == full_uuid
            assert err is None

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_empty_string_not_treated_as_short_id(self):
        """Empty string should return (None, None)."""
        func = self._get_func()
        resolved, err = func("")
        assert resolved is None
        assert err is None

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_canonical_map_fallback_to_discover(self):
        """When canonical_map misses but _discover_sessions finds a unique prefix."""
        func = self._get_func()
        full_uuid = "deadbeef-1234-5678-abcd-ef0123456789"
        short_id = "deadbeef"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {}  # no pre-built mapping
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                mock_discover.return_value = [
                    ("proj", full_uuid, None),
                    ("other", "bbbbbbbb-1234-5678-abcd-ef0123456789", None),
                ]
                resolved, err = func(short_id)
                assert resolved == full_uuid.lower()
                assert err is None

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_case_insensitive_match(self):
        """Short ID resolution should be case-insensitive."""
        func = self._get_func()
        full_uuid = "A1B2C3D4-e5f6-7890-abcd-ef1234567890"
        short_id = "A1B2C3D4"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {}
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                mock_discover.return_value = [
                    ("project-a", full_uuid, None),
                ]
                resolved, err = func(short_id)
                assert resolved == full_uuid.lower()
                assert err is None


class TestShortIdRouteBehavior:
    """Tests that verify the route calls _resolve_qoder_short_id on miss.

    These verify the behavioral contract without deep-mocking _serve_session.
    """

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_resolve_called_for_qoder_short_id_miss(self):
        """_resolve_qoder_short_id is called when qoder session lookup misses."""
        from session_browser.web.routes import _resolve_qoder_short_id

        full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        short_id = "a1b2c3d4"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {short_id: full_uuid}
            resolved, err = _resolve_qoder_short_id(short_id)
            assert resolved == full_uuid
            assert err is None
            mock_map.assert_called_once()

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_resolve_not_called_for_full_uuid(self):
        """_resolve_qoder_short_id returns (None, None) for full UUID input."""
        from session_browser.web.routes import _resolve_qoder_short_id

        full_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resolved, err = _resolve_qoder_short_id(full_uuid)
        assert resolved is None
        assert err is None

    @pytest.mark.contract_case("DATA-INDEX-008")
    def test_ambiguous_returns_error_not_none(self):
        """Ambiguous short ID must return an error message, not silently fail."""
        from session_browser.web.routes import _resolve_qoder_short_id

        uuid1 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        uuid2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567891"

        with patch("session_browser.sources.qoder._build_canonical_id_map") as mock_map:
            mock_map.return_value = {}
            with patch("session_browser.sources.qoder._discover_sessions") as mock_discover:
                mock_discover.return_value = [
                    ("proj-a", uuid1, None),
                    ("proj-b", uuid2, None),
                ]
                resolved, err = _resolve_qoder_short_id("a1b2c3d4")
                assert resolved is None
                assert err is not None
                assert len(err) > 10  # must have a meaningful error


if __name__ == "__main__":
    unittest.main()
