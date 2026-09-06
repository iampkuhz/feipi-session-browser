"""credential scanner 合成回归测试。

验证：
1. 非 UTF-8 文件触发 fail-closed，报告文件路径与错误类别。
2. 正常密钥检测不受影响。
3. 不削弱检测能力。"""

from __future__ import annotations

from scripts.gates.checks.privacy.check_credential_leak import _scan_file, check


def test_non_utf8_file_triggers_fail_closed(tmp_path, monkeypatch):
    """非 UTF-8 的 .py 文件应触发 fail-closed，报告文件路径与错误类别。"""
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.ROOT', tmp_path)
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.SCAN_DIRS', ['src'])

    # 创建含非 UTF-8 字节的 .py 文件
    src_dir = tmp_path / 'src'
    src_dir.mkdir()
    bad_file = src_dir / 'bad.py'
    # 写入包含非 UTF-8 字节的内容（0x92 是 Windows-1252 的右单引号）
    # 使用拼接避免触发扫描器
    bad_file.write_bytes(b'token = "' + b'sk-' + b'ant-' + b'\x92' * 20 + b'"\n')

    # _scan_file 应返回非空诊断
    diagnostics = _scan_file(bad_file)
    assert len(diagnostics) == 1
    assert 'bad.py' in diagnostics[0]
    assert '编码错误' in diagnostics[0]

    # check() 应返回 FAIL
    result = check([])
    assert result.status == 'FAIL'
    assert result.reason == 'input-unavailable'
    assert any('编码错误' in d.message for d in result.diagnostics)


def test_normal_credential_detection_unaffected(tmp_path, monkeypatch):
    """正常密钥检测不受非 UTF-8 处理影响。"""
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.ROOT', tmp_path)
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.SCAN_DIRS', ['src'])

    src_dir = tmp_path / 'src'
    src_dir.mkdir()

    # 创建含真实密钥模式的 UTF-8 文件（使用拼接避免触发扫描器）
    good_file = src_dir / 'config.py'
    good_file.write_text('token = "' + 'sk-' + 'ant-' + 'RealSecretValue123"\n', encoding='utf-8')

    diagnostics = _scan_file(good_file)
    assert len(diagnostics) > 0
    assert 'Anthropic token' in diagnostics[0]

    # check() 应返回 BLOCKED（发现密钥）
    result = check([])
    assert result.status == 'BLOCKED'


def test_mixed_utf8_and_non_utf8_files(tmp_path, monkeypatch):
    """混合 UTF-8 和非 UTF-8 文件时，应报告所有问题并 fail-closed。"""
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.ROOT', tmp_path)
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.SCAN_DIRS', ['src'])

    src_dir = tmp_path / 'src'
    src_dir.mkdir()

    # UTF-8 文件含密钥（使用拼接避免触发扫描器）
    good_file = src_dir / 'good.py'
    good_file.write_text('api_key = "' + 'sk-' + 'RealSecret1234567890"\n', encoding='utf-8')

    # 非 UTF-8 文件
    bad_file = src_dir / 'bad.txt'
    bad_file.write_bytes(b'some text with \xff\xfe invalid bytes\n')

    result = check([])
    # 应 fail-closed（因为有编码错误）
    assert result.status == 'FAIL'
    assert result.reason == 'input-unavailable'
    # 应包含两种诊断
    assert any('编码错误' in d.message for d in result.diagnostics)
    assert any('密钥赋值' in d.message for d in result.diagnostics)


def test_scan_does_not_print_file_content(tmp_path, monkeypatch, capsys):
    """扫描不应打印文件内容，只报告路径和错误类别。"""
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.ROOT', tmp_path)
    monkeypatch.setattr('scripts.gates.checks.privacy.check_credential_leak.SCAN_DIRS', ['src'])

    src_dir = tmp_path / 'src'
    src_dir.mkdir()
    bad_file = src_dir / 'secret.py'
    # 包含敏感内容的非 UTF-8 文件（使用拼接避免触发扫描器）
    bad_file.write_bytes(
        b'name = "' + b'AWS' + b'_SECRET' + b'_ACCESS' + b'_KEY" value="' + b'\x92' * 30 + b'"\n'
    )

    result = check([])
    captured = capsys.readouterr()

    # 输出不应包含实际的密钥值
    assert 'AKIA' not in captured.out
    assert 'AKIA' not in captured.err
    # 但应包含文件路径
    assert 'secret.py' in str([d.message for d in result.diagnostics])


def test_only_known_cache_roots_are_excluded(tmp_path, monkeypatch):
    """缓存根位置排除，但源码中同名目录的文本仍必须扫描。"""
    from scripts.gates.checks.privacy import check_credential_leak as scanner

    monkeypatch.setattr(scanner, 'ROOT', tmp_path)
    monkeypatch.setattr(scanner, 'SCAN_DIRS', ['java', 'docs', 'scripts'])
    generated = [
        'java/.local/runtime.txt',
        'java/tests/.local/runtime.txt',
        'java/gradle/aggregates/.local/runtime.txt',
        'scripts/.local/runtime.txt',
        'java/tests/playwright/node_modules/tool/runtime.txt',
    ]
    for relative in generated:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'\xff synthetic tool output')
        assert scanner._is_excluded_path(path)
    assert scanner.check([]).status == 'PASS'

    source_paths = [
        'docs/node_modules/guide.md',
        'java/application/src/test/resources/.local/credential.json',
        'scripts/tests/fixtures/__pycache__/config.py',
        'scripts/tests/fixtures/.venv/config.py',
    ]
    for relative in source_paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('token = "' + 'sk-' + 'ant-' + 'SyntheticSecret123456"\n')
        assert not scanner._is_excluded_path(path)
        assert scanner._scan_file(path)
    result = scanner.check([])
    assert result.status == 'BLOCKED'
    for relative in source_paths:
        assert any(relative in diagnostic.message for diagnostic in result.diagnostics)
