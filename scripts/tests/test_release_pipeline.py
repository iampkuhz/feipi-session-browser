"""合成归档验证单平台发行安全边界，不替代真实 macOS arm64 包验收。"""

from __future__ import annotations

import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest
from scripts.release import release_pipeline_helpers as h

PROVENANCE = h.Provenance('0.5', 'a' * 40, '100', '1')
SCRIPT = Path(h.__file__)
SERVE_HELP = 'Usage: app-cli serve --no-scan --index-dir'
JVM_ARCH_PROPERTY = "    printf '    os.arch = aarch64\\n' >&2\n"
MODEL = f'''#!/bin/sh
[ -z "${{JAVA_HOME:-}}${{CLASSPATH:-}}${{_JAVA_OPTIONS:-}}" ] || exit 6
java
[ "$?" = 97 ] || exit 7
case "$1" in
  --version) printf '0.5 版本\\n' ;;
  --help) printf 'Usage: app-cli scan serve\\n' ;;
  serve)
    [ "$2" = --no-scan ] && [ "$3" = --index-dir ] && [ "$5" = --help ] || exit 8
    [ "$JDK_JAVA_OPTIONS" = -XshowSettings:properties ] || exit 9
    [ "$JAVA_TOOL_OPTIONS" = "-Duser.home=\\\"$HOME\\\"" ] || exit 10
{JVM_ARCH_PROPERTY}    printf '    user.home = %s\\n' "$HOME" >&2
    printf '{SERVE_HELP}\\n' ;;
  *) exit 11 ;;
esac
'''


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setattr(h, 'is_macos_arm64', lambda: True)


def _tar(path, entries):
    with tarfile.open(path, 'w:gz') as archive:
        for name, kind, payload, mode in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.mode = mode
            data = payload.encode('utf-8')
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = payload
            if kind == tarfile.REGTYPE:
                info.size = len(data)
            archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)


def _file(name, payload='fixture', mode=0o644):
    return name, tarfile.REGTYPE, payload, mode


def _package(path, *, launcher=MODEL, mode=0o755, version='0.5', extra=()):
    _tar(
        path,
        [
            _file('app-cli/VERSION', version),
            _file('app-cli/bin/run', launcher, mode),
            _file('app-cli/runtime/bin/java', '#!/bin/sh\nexit 99\n', 0o755),
            _file('app-cli/app/lib/model.jar'),
            *extra,
        ],
    )


def _raw(root, **kwargs):
    root.mkdir()
    package = root / 'app-cli-runtime-0.5.tgz'
    _package(package, **kwargs)
    return package


@pytest.mark.parametrize(
    'name',
    [
        '/escape',
        '../escape',
        'safe/../escape',
        r'C:\escape',
        'C:/escape',
        r'\\host\escape',
        'name\nfile',
    ],
)
def test_unsafe_paths_rejected_before_writes(tmp_path, name):
    archive = tmp_path / 'unsafe.tar.gz'
    _tar(archive, [_file('safe'), _file(name)])
    out = tmp_path / 'out'
    assert not h.safe_extract_tar(archive, out)[0]
    assert not out.exists()


@pytest.mark.parametrize(
    'entries',
    [
        [_file('same'), _file('./same')],
        [_file('Same'), _file('same')],
        [_file('parent'), _file('parent/child')],
        [('alias', tarfile.SYMTYPE, '.', 0o777), _file('alias/../escape')],
        [('link', tarfile.SYMTYPE, 'inside', 0o777)],
        [('link', tarfile.LNKTYPE, 'inside', 0o777)],
        [('special', tarfile.FIFOTYPE, '', 0o644)],
        [('special', tarfile.CHRTYPE, '', 0o644)],
    ],
)
def test_ambiguous_targets_links_and_special_files_rejected(tmp_path, entries):
    archive = tmp_path / 'unsafe.tar.gz'
    _tar(archive, entries)
    out = tmp_path / 'out'
    assert not h.safe_extract_tar(archive, out)[0]
    assert not out.exists()


@pytest.mark.parametrize(
    'content',
    [
        '',
        '# header\n',
        'x',
        f'{"a" * 64}  +1  a.tar.gz',
        f'{"a" * 64}  1  ../a.tar.gz',
        f'{"a" * 64}  1  a.zip',
    ],
)
def test_manifest_syntax(tmp_path, content):
    manifest = tmp_path / 'MANIFEST.SHA256'
    manifest.write_text(content)
    assert h.parse_manifest(manifest)[1]


@pytest.mark.parametrize(
    'fault', ['extra', 'missing', 'directory', 'symlink', 'size', 'hash', 'duplicate']
)
def test_manifest_membership_and_integrity(tmp_path, fault):
    asset = tmp_path / 'a.tar.gz'
    asset.write_bytes(b'a')
    line = f'{h.compute_sha256(asset)}  1  a.tar.gz\n'
    if fault == 'extra':
        (tmp_path / 'b.tar.gz').write_bytes(b'b')
    elif fault in ('missing', 'directory', 'symlink'):
        asset.unlink()
        if fault == 'directory':
            asset.mkdir()
        if fault == 'symlink':
            asset.symlink_to(tmp_path / 'target')
    elif fault == 'size':
        line = line.replace('  1  ', '  2  ')
    elif fault == 'hash':
        line = '0' * 64 + '  1  a.tar.gz\n'
    else:
        line *= 2
    manifest = tmp_path / 'MANIFEST.SHA256'
    manifest.write_text(line)
    assert not h.verify_manifest_against_files(manifest, tmp_path)[0]


def test_checksum_wrapper_uses_bash32_compatible_entry(tmp_path):
    (tmp_path / 'a.tar.gz').write_bytes(b'a')
    wrapper = SCRIPT.parent / 'generate-checksums.sh'
    for args in ([], ['--verify']):
        result = subprocess.run(
            ['/bin/bash', str(wrapper), str(tmp_path), *args], capture_output=True
        )
        assert result.returncode == 0, result.stderr
    (tmp_path / 'MANIFEST.SHA256').write_text('')
    assert subprocess.run(
        ['/bin/bash', str(wrapper), str(tmp_path), '--verify'], capture_output=True
    ).returncode


@pytest.mark.parametrize(
    'os_name,arch,expected',
    [
        ('Darwin', 'arm64', True),
        ('Darwin', 'aarch64', True),
        ('Darwin', 'x86_64', False),
        ('Linux', 'arm64', False),
    ],
)
def test_native_host_check_does_not_accept_other_system_or_cpu(
    monkeypatch, os_name, arch, expected
):
    monkeypatch.setattr(h.system_platform, 'system', lambda: os_name)
    monkeypatch.setattr(h.system_platform, 'machine', lambda: arch)
    assert h.is_macos_arm64() is expected


def test_single_seal_binds_exact_bytes_and_real_launcher_model(tmp_path, native, monkeypatch):
    monkeypatch.setenv('JAVA_HOME', 'synthetic-jdk-must-not-leak')
    monkeypatch.setenv('CLASSPATH', 'synthetic-classpath-must-not-leak')
    monkeypatch.setenv('_JAVA_OPTIONS', 'synthetic-jvm-args-must-not-leak')
    raw = _raw(tmp_path / 'raw')
    root = tmp_path / 'verified'
    asset = h.prepare_candidate(raw.parent, root, PROVENANCE)
    assert asset.name == 'app-cli-0.5-runtime-macos-arm64.tar.gz'
    assert asset.read_bytes() == raw.read_bytes()
    assert {file.name for file in root.iterdir()} == {
        asset.name,
        asset.name + '.provenance.json',
        asset.name + '.smoke.json',
        'MANIFEST.SHA256',
    }
    receipt = json.loads(h.sidecar(asset, '.smoke.json').read_text())
    assert (
        receipt['host_platform']
        == receipt['platform']
        == receipt['producer_platform']
        == 'macos-arm64'
    )
    assert receipt['isolated_jvm_home'] is True
    assert receipt['version_output'] == '0.5 版本' and receipt['serve_help_output'] == SERVE_HELP
    monkeypatch.setattr(h, 'is_macos_arm64', lambda: False)
    assert h.verify_candidate_set(root, PROVENANCE) == (
        True,
        [],
        {'native_platform': 'macos-arm64', 'total_packages': 1},
    )
    with pytest.raises(ValueError, match='requires native macOS arm64'):
        h.prepare_candidate(raw.parent, tmp_path / 'unsupported', PROVENANCE)


@pytest.mark.parametrize(
    'fault,pattern',
    [
        ('not-executable', 'non-executable'),
        ('wrong-version-file', 'mismatched VERSION'),
        ('wrong-version', 'output mismatch'),
        ('wrong-serve-help', 'output mismatch'),
        ('wrong-home', 'isolated JVM home'),
        ('duplicate-home', 'isolated JVM home'),
        ('x86-jvm-on-arm-host', 'JVM os.arch must be aarch64 or arm64'),
        ('missing-jvm-arch', 'JVM os.arch must be aarch64 or arm64'),
        ('duplicate-jvm-arch', 'JVM os.arch must be aarch64 or arm64'),
        ('created-index', 'created an index'),
        ('launcher-error', 'returncode=2'),
        ('invalid-utf8', 'not UTF-8'),
        ('unsafe-tar', 'path traversal'),
    ],
)
def test_prepare_rejects_bad_archive_and_leaves_no_candidate(tmp_path, native, fault, pattern):
    script = {
        'wrong-version': MODEL.replace('0.5 版本', '0.50 版本'),
        'wrong-serve-help': MODEL.replace(SERVE_HELP, 'Usage: serve'),
        'wrong-home': MODEL.replace(' "$HOME" >&2', ' "wrong" >&2'),
        'duplicate-home': MODEL.replace(
            '    printf \'    user.home',
            '    printf "    user.home = fake\\n" >&2\n    printf \'    user.home',
        ),
        'x86-jvm-on-arm-host': MODEL.replace('os.arch = aarch64', 'os.arch = x86_64'),
        'missing-jvm-arch': MODEL.replace(JVM_ARCH_PROPERTY, ''),
        'duplicate-jvm-arch': MODEL.replace(JVM_ARCH_PROPERTY, JVM_ARCH_PROPERTY * 2),
        'created-index': MODEL.replace(
            '    printf \'    user.home', '    : > "$4"\n    printf \'    user.home'
        ),
        'launcher-error': '#!/bin/sh\necho synthetic-private-output >&2\nexit 2\n',
        'invalid-utf8': '#!/bin/sh\nprintf "\\377"\n',
    }.get(fault, MODEL)
    raw = _raw(
        tmp_path / 'raw',
        launcher=script,
        mode=0o644 if fault == 'not-executable' else 0o755,
        version='0.4' if fault == 'wrong-version-file' else '0.5',
        extra=[_file('../escape')] if fault == 'unsafe-tar' else (),
    )
    output = tmp_path / 'verified'
    with pytest.raises(ValueError, match=pattern) as error:
        h.prepare_candidate(raw.parent, output, PROVENANCE)
    assert 'synthetic-private-output' not in str(error.value)
    assert not output.exists()
    assert not list(tmp_path.glob('release-prepare-*'))


@pytest.mark.parametrize(
    'fault',
    [
        'extra',
        'missing',
        'symlink',
        'hash',
        'run',
        'attempt',
        'sha',
        'platform',
        'unisolated',
        'boolean-type',
        'invalid-help',
        'duplicate-json',
    ],
)
def test_verify_rejects_bad_files_bytes_identity_or_smoke(tmp_path, native, fault):
    raw = _raw(tmp_path / 'raw')
    output = tmp_path / 'verified'
    asset = h.prepare_candidate(raw.parent, output, PROVENANCE)
    smoke = h.sidecar(asset, '.smoke.json')
    if fault == 'extra':
        (output / 'app-cli-0.5-generic.zip').touch()
    elif fault == 'missing':
        smoke.unlink()
    elif fault == 'symlink':
        data = smoke.read_bytes()
        smoke.unlink()
        external = tmp_path / 'copy'
        external.write_bytes(data)
        smoke.symlink_to(external)
    elif fault == 'hash':
        data = asset.read_bytes()
        asset.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    elif fault == 'duplicate-json':
        data = smoke.read_text().rstrip()
        smoke.write_text(data[:-1] + ', "isolated_jvm_home": true}')
    else:
        key, value = {
            'run': ('run_id', '20'),
            'attempt': ('run_attempt', '2'),
            'sha': ('source_sha', 'b' * 40),
            'platform': ('host_platform', 'linux-x64'),
            'unisolated': ('isolated_jvm_home', False),
            'boolean-type': ('isolated_jvm_home', 1),
            'invalid-help': ('serve_help_output', 'Usage: fake'),
        }[fault]
        data = json.loads(smoke.read_text())
        data[key] = value
        smoke.write_text(json.dumps(data))
    assert not h.verify_candidate_set(output, PROVENANCE)[0]


def test_prepare_copies_bytes_before_inspection(tmp_path, native, monkeypatch):
    raw = _raw(tmp_path / 'raw')
    original = raw.read_bytes()
    inspect = h._inspect

    def replace_raw(*args, **kwargs):
        result = inspect(*args, **kwargs)
        raw.write_bytes(b'source changed after inspect')
        return result

    monkeypatch.setattr(h, '_inspect', replace_raw)
    output = h.prepare_candidate(raw.parent, tmp_path / 'verified', PROVENANCE)
    assert output.read_bytes() == original


def test_consistent_metadata_cannot_admit_an_unsafe_tar(tmp_path, native):
    raw = _raw(tmp_path / 'raw')
    root = tmp_path / 'verified'
    asset = h.prepare_candidate(raw.parent, root, PROVENANCE)
    _tar(asset, [_file('../escape')])
    entry = h._measure(asset)
    h._write_manifest(root, [entry])
    for suffix in ('.provenance.json', '.smoke.json'):
        sidecar = h.sidecar(asset, suffix)
        data = json.loads(sidecar.read_text())
        sidecar.write_text(json.dumps(data | {'sha256': entry.sha256, 'size': entry.size}))
    success, errors, _ = h.verify_candidate_set(root, PROVENANCE)
    assert not success and 'path traversal' in errors[0]
