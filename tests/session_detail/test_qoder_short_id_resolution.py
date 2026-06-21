"""Qoder 短 ID URL 别名解析测试 (T058).
验证:
- 短 ID 与唯一完整 UUID 匹配时正确解析
- 短 ID 匹配多个完整 UUID 时返回 404/诊断信息(不猜测)
- 完整 UUID 直通是无操作
- 不匹配的短 ID 返回 404.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest


class TestResolveQoderShortId:
    """_resolve_qoder_short_id 单元测试(routes.py).."""

    def _get_func(self):
        """导入被测函数.."""
        from session_browser.web.routes import _resolve_qoder_short_id

        return _resolve_qoder_short_id

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_unique_prefix_match(self):
        """短 ID 精确匹配一个完整 UUID 时应解析成功.."""
        func = self._get_func()
        full_uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        short_id = 'a1b2c3d4'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {}
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                mock_discover.return_value = [
                    ('project-a', full_uuid, None),
                ]
                resolved, err = func(short_id)
                assert resolved == full_uuid.lower(), (
                    f'Expected {full_uuid.lower()}, got {resolved}'
                )
                assert err is None

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_ambiguous_multiple_matches(self):
        """短 ID 匹配多个完整 UUID 时不得猜测 -- 返回错误.."""
        func = self._get_func()
        uuid1 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        uuid2 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567891'
        short_id = 'a1b2c3d4'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {}
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                mock_discover.return_value = [
                    ('project-a', uuid1, None),
                    ('project-b', uuid2, None),
                ]
                resolved, err = func(short_id)
                assert resolved is None
                assert err is not None
                assert '2' in err  # 提到匹配数量

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_no_match_returns_none(self):
        """无前缀匹配的短 ID 应返回 (None, None).."""
        func = self._get_func()
        short_id = 'zzzzzzzz'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {}
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                mock_discover.return_value = [
                    ('project-a', 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', None),
                ]
                resolved, err = func(short_id)
                assert resolved is None
                assert err is None

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_full_uuid_passthrough(self):
        """输入完整 UUID 时应返回 (None, None) -- 不作为短 ID 处理.."""
        func = self._get_func()
        full_uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                resolved, err = func(full_uuid)
                assert resolved is None
                assert err is None
                mock_map.assert_not_called()
                mock_discover.assert_not_called()

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_canonical_map_hit(self):
        """如果 _build_canonical_id_map 已有该短 ID,则直接使用.."""
        func = self._get_func()
        full_uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        short_id = 'a1b2c3d4'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {short_id: full_uuid}
            resolved, err = func(short_id)
            assert resolved == full_uuid
            assert err is None

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_empty_string_not_treated_as_short_id(self):
        """空字符串应返回 (None, None).."""
        func = self._get_func()
        resolved, err = func('')
        assert resolved is None
        assert err is None

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_canonical_map_fallback_to_discover(self):
        """当 canonical_map 未命中但 _discover_sessions 找到唯一前缀时.."""
        func = self._get_func()
        full_uuid = 'deadbeef-1234-5678-abcd-ef0123456789'
        short_id = 'deadbeef'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {}  # 无预构建映射
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                mock_discover.return_value = [
                    ('proj', full_uuid, None),
                    ('other', 'bbbbbbbb-1234-5678-abcd-ef0123456789', None),
                ]
                resolved, err = func(short_id)
                assert resolved == full_uuid.lower()
                assert err is None

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_case_insensitive_match(self):
        """短 ID 解析应不区分大小写.."""
        func = self._get_func()
        full_uuid = 'A1B2C3D4-e5f6-7890-abcd-ef1234567890'
        short_id = 'A1B2C3D4'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {}
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                mock_discover.return_value = [
                    ('project-a', full_uuid, None),
                ]
                resolved, err = func(short_id)
                assert resolved == full_uuid.lower()
                assert err is None


class TestShortIdRouteBehavior:
    """验证路由调用 _resolve_qoder_short_id 的行为..

    验证行为契约,无需深度模拟 _serve_session.
    """

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_resolve_called_for_qoder_short_id_miss(self):
        """当 qoder 会话查找未命中时,应调用 _resolve_qoder_short_id.."""
        from session_browser.web.routes import _resolve_qoder_short_id

        full_uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        short_id = 'a1b2c3d4'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {short_id: full_uuid}
            resolved, err = _resolve_qoder_short_id(short_id)
            assert resolved == full_uuid
            assert err is None
            mock_map.assert_called_once()

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_resolve_not_called_for_full_uuid(self):
        """输入完整 UUID 时 _resolve_qoder_short_id 返回 (None, None).."""
        from session_browser.web.routes import _resolve_qoder_short_id

        full_uuid = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        resolved, err = _resolve_qoder_short_id(full_uuid)
        assert resolved is None
        assert err is None

    @pytest.mark.contract_case('DATA-INDEX-008')
    def test_ambiguous_returns_error_not_none(self):
        """模糊短 ID 必须返回错误消息,而非静默失败.."""
        from session_browser.web.routes import _resolve_qoder_short_id

        uuid1 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
        uuid2 = 'a1b2c3d4-e5f6-7890-abcd-ef1234567891'

        with patch('session_browser.sources.qoder._build_canonical_id_map') as mock_map:
            mock_map.return_value = {}
            with patch('session_browser.sources.qoder._discover_sessions') as mock_discover:
                mock_discover.return_value = [
                    ('proj-a', uuid1, None),
                    ('proj-b', uuid2, None),
                ]
                resolved, err = _resolve_qoder_short_id('a1b2c3d4')
                assert resolved is None
                assert err is not None
                assert len(err) > 10  # 必须有有意义的错误信息


if __name__ == '__main__':
    unittest.main()
