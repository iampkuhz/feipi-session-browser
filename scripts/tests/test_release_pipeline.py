"""验证发布工程工具的安全边界；合成包仅测试契约，不证明原生发行包可运行。"""

from __future__ import annotations

import io
import json
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts.release import release_pipeline_helpers as h

PROVENANCE = h.Provenance('0.4', 'a' * 40, '100', '1')
SCRIPT = Path(h.__file__)


def _tar(path, entries):
    with tarfile.open(path, 'w:gz') as archive:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            if name.endswith(('/bin/run', '/bin/java')):
                info.mode = 0o755
            if kind == tarfile.SYMTYPE:
                info.linkname = payload
            elif kind == tarfile.REGTYPE:
                data = payload.encode()
                info.size = len(data)
            archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)


@pytest.mark.parametrize(
    'name', ['/escape', '../escape', 'safe/../escape', r'C:\escape', 'C:/escape', r'\\host\escape']
)
@pytest.mark.parametrize('fmt', ['tar', 'zip'])
def test_unsafe_paths_rejected_before_writes(tmp_path, name, fmt):
    archive = tmp_path / ('evil.tar.gz' if fmt == 'tar' else 'evil.zip')
    if fmt == 'tar':
        _tar(archive, [('good', tarfile.REGTYPE, 'ok'), (name, tarfile.REGTYPE, 'bad')])
        result = h.safe_extract_tar(archive, tmp_path / 'out')
    else:
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('good', 'ok')
            output.writestr(name, 'bad')
        result = h.safe_extract_zip(archive, tmp_path / 'out')
    assert not result[0]
    assert not (tmp_path / 'out/good').exists()
    assert not (tmp_path / 'escape').exists()


def test_alias_dotdot_escape_is_red_regression(tmp_path):
    archive = tmp_path / 'evil.tar.gz'
    _tar(archive, [('alias', tarfile.SYMTYPE, '.'), ('alias/../escape', tarfile.REGTYPE, 'bad')])
    assert not h.safe_extract_tar(archive, tmp_path / 'out')[0]
    assert not (tmp_path / 'escape').exists()


@pytest.mark.parametrize('kind', [tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE])
def test_tar_special_rejected(tmp_path, kind):
    archive = tmp_path / 'evil.tar.gz'
    _tar(archive, [('special', kind, '')])
    assert not h.safe_extract_tar(archive, tmp_path / 'out')[0]


@pytest.mark.parametrize('fmt', ['tar', 'zip'])
def test_duplicate_target_rejected(tmp_path, fmt):
    archive = tmp_path / 'evil'
    if fmt == 'tar':
        _tar(archive, [('same', tarfile.REGTYPE, 'one'), ('./same', tarfile.REGTYPE, 'two')])
        result = h.safe_extract_tar(archive, tmp_path / 'out')
    else:
        with zipfile.ZipFile(archive, 'w') as output:
            output.writestr('same', 'one')
            output.writestr('./same', 'two')
        result = h.safe_extract_zip(archive, tmp_path / 'out')
    assert not result[0]
    assert not (tmp_path / 'out/same').exists()


@pytest.mark.parametrize('fmt', ['tar', 'zip'])
@pytest.mark.parametrize('target', ['../../escape', '/escape', r'C:\escape', 'inside'])
def test_links_are_explicitly_rejected(tmp_path, fmt, target):
    archive = tmp_path / 'link'
    if fmt == 'tar':
        _tar(archive, [('link', tarfile.SYMTYPE, target)])
        result = h.safe_extract_tar(archive, tmp_path / 'out')
    else:
        with zipfile.ZipFile(archive, 'w') as output:
            info = zipfile.ZipInfo('link')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(info, target)
        result = h.safe_extract_zip(archive, tmp_path / 'out')
    assert not result[0]


@pytest.mark.parametrize(
    'bad',
    [
        '',
        '# header\n',
        'a  1  a.zip',
        f'{"a" * 64}  +1  a.zip',
        f'{"a" * 64}  1  a.zip extra',
        f'{"a" * 64}  1  ../a.zip',
    ],
)
def test_manifest_syntax(tmp_path, bad):
    manifest = tmp_path / 'MANIFEST.SHA256'
    manifest.write_text(bad)
    assert h.parse_manifest(manifest)[1]


@pytest.mark.parametrize(
    'fault', ['extra', 'missing', 'directory', 'symlink', 'size', 'hash', 'duplicate']
)
def test_manifest_membership_and_integrity(tmp_path, fault):
    asset = tmp_path / 'a.zip'
    asset.write_bytes(b'a')
    line = f'{h.compute_sha256(asset)}  1  a.zip\n'
    if fault == 'extra':
        (tmp_path / 'b.zip').write_bytes(b'b')
    elif fault == 'missing':
        asset.unlink()
    elif fault == 'directory':
        asset.unlink()
        asset.mkdir()
    elif fault == 'symlink':
        asset.unlink()
        (tmp_path / 'target').write_bytes(b'a')
        asset.symlink_to(tmp_path / 'target')
    elif fault == 'size':
        line = line.replace('  1  ', '  2  ')
    elif fault == 'hash':
        line = '0' * 64 + '  1  a.zip\n'
    else:
        line *= 2
    manifest = tmp_path / 'MANIFEST.SHA256'
    manifest.write_text(line)
    assert not h.verify_manifest_against_files(manifest, tmp_path)[0]


def _model_runtime(
    root, *, version='0.4', output='0.4', help_output='Usage: app-cli scan serve', fail=False
):
    package = root / 'app-cli'
    for directory in ['bin', 'runtime/bin', 'app/lib']:
        (package / directory).mkdir(parents=True, exist_ok=True)
    (package / 'VERSION').write_text(version)
    (package / 'app/lib/model.jar').write_bytes(b'model-only')
    java = package / 'runtime/bin/java'
    java.write_text('#!/bin/sh\nexit 99\n')
    java.chmod(0o755)
    launcher = package / 'bin/run'
    launcher.write_text(
        f'#!/bin/sh\ncase "$1" in --version) echo "{output}";; --help) echo "{help_output}";; esac\nexit {1 if fail else 0}\n'
    )
    launcher.chmod(0o755)
    return package


@pytest.mark.parametrize(
    'fault', ['missing', 'failure', 'version', 'help', 'runtime', 'package-version']
)
def test_launcher_negative_model(tmp_path, fault):
    package = _model_runtime(
        tmp_path,
        output='WRONG' if fault == 'version' else '0.4',
        help_output='wrong' if fault == 'help' else 'Usage: app-cli scan serve',
        fail=fault == 'failure',
        version='0.3' if fault == 'package-version' else '0.4',
    )
    if fault == 'missing':
        (package / 'bin/run').unlink()
    if fault == 'runtime':
        (package / 'runtime/bin/java').unlink()
    assert not h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4').success


def test_launcher_model_executes_launcher_not_java(tmp_path):
    _model_runtime(tmp_path)
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert result.success, result.error
    assert result.launcher_version_output == '0.4'


def test_launcher_accepts_sgr_but_preserves_original_receipt_output(tmp_path):
    version = '\x1b[1m0.4\x1b[21m'
    help_output = '\x1b[1mUsage:\x1b[0m app-cli \x1b[39mscan\x1b[m \x1b[31;1mserve\x1b[0m'
    _model_runtime(tmp_path, output=version, help_output=help_output)
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert result.success, result.error
    assert result.launcher_version_output == version
    assert result.launcher_help_output == help_output


@pytest.mark.parametrize(
    'version,help_output',
    [
        ('\x1b[1m0.40\x1b[0m', 'Usage: app-cli scan serve'),
        ('0.4', '\x1b[1mWrong:\x1b[0m app-cli scan serve'),
        ('0.4', 'Usage: app-cli \x1b[1mscan\x1b[0m'),
        ('0.4', 'Usage: app-cli \x1b[1mserve\x1b[0m'),
        ('0.4', 'Usage: app-cli sc\x1b[2Jan serve'),
        ('0.4', 'Usage: app-cli sc\x1b]0;title\x07an serve'),
    ],
)
def test_sgr_normalization_keeps_original_output_requirements(version, help_output):
    assert not h._valid_outputs(version, help_output, '0.4')


@pytest.mark.parametrize('fail', [False, True])
def test_launcher_failure_diagnostics_do_not_echo_output(tmp_path, fail):
    private = 'synthetic-private-output'
    _model_runtime(tmp_path, help_output=private, fail=fail)
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert not result.success
    assert private not in result.error
    assert 'chars' in result.error


def test_launcher_decodes_real_utf8_output_independently_of_locale(tmp_path, monkeypatch):
    help_output = 'Usage: app-cli scan serve 中文：功能说明'
    package = _model_runtime(tmp_path)
    (package / 'bin/run').write_bytes(
        (
            '#!/bin/sh\ncase "$1" in --version) echo "0.4 版本";; '
            f'--help) echo "{help_output}";; esac\n'
            'printf "诊断信息" >&2\n'
        ).encode()
    )
    monkeypatch.setenv('LC_ALL', 'C')
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert result.success, result.error
    assert result.launcher_version_output == '0.4 版本'
    assert result.launcher_help_output == help_output


@pytest.mark.parametrize('argument', ['--version', '--help'])
@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_launcher_rejects_real_invalid_utf8_output(tmp_path, argument, stream):
    package = _model_runtime(tmp_path)
    launcher = package / 'bin/run'
    redirect = ' >&2' if stream == 'stderr' else ''
    launcher.write_bytes(
        launcher.read_bytes().replace(
            b'exit 0', f'if [ "$1" = "{argument}" ]; then printf "\\377"{redirect}; fi'.encode()
        )
    )
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert not result.success
    assert 'utf-8' in result.error
    assert 'invalid start byte' in result.error


def _candidate(root):
    root.mkdir()
    for platform in sorted(h.NATIVE_PLATFORMS | {'generic'}):
        name = h.archive_name(PROVENANCE, platform)
        archive = root / name
        package_root = 'app-cli-0.4' if platform == 'generic' else 'app-cli'
        if name.endswith('.zip'):
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr(package_root + '/VERSION', '0.4')
                output.writestr(
                    package_root
                    + ('/lib/model.jar' if platform == 'generic' else '/app/lib/model.jar'),
                    'model',
                )
                if platform != 'generic':
                    output.writestr(package_root + '/bin/run.bat', '@echo off')
                    output.writestr(package_root + '/runtime/bin/java.exe', 'model')
        else:
            _tar(
                archive,
                [
                    (package_root + '/VERSION', tarfile.REGTYPE, '0.4'),
                    (package_root + '/bin/run', tarfile.REGTYPE, 'model'),
                    (package_root + '/runtime/bin/java', tarfile.REGTYPE, 'model'),
                    (package_root + '/app/lib/model.jar', tarfile.REGTYPE, 'model'),
                ],
            )
        h.write_provenance(archive, PROVENANCE, platform)
        if platform != 'generic':
            h.write_smoke_receipt(archive, PROVENANCE, platform, '0.4', 'Usage: app-cli scan serve')
    h.generate_manifest(root)
    return root


def test_complete_model_set_and_copy(tmp_path):
    candidate = _candidate(tmp_path / 'candidate')
    assert h.verify_candidate_set(candidate, PROVENANCE)[0]
    success, errors, output = h.create_verified_candidate(
        candidate, PROVENANCE, tmp_path / 'verified'
    )
    assert success, errors
    assert h.verify_candidate_set(output, PROVENANCE)[0]


@pytest.mark.parametrize(
    'fault',
    [
        'missing-platform',
        'manifest',
        'corrupt',
        'name',
        'sha',
        'run',
        'attempt',
        'receipt',
        'version',
        'extra',
    ],
)
def test_candidate_rejects_bad_inputs_without_laundering(tmp_path, fault):
    candidate = _candidate(tmp_path / 'candidate')
    asset = candidate / h.archive_name(PROVENANCE, 'linux-x64')
    if fault == 'missing-platform':
        asset.unlink()
    elif fault == 'manifest':
        (candidate / 'MANIFEST.SHA256').write_text('bad\n')
    elif fault == 'corrupt':
        asset.write_bytes(b'corrupt')
        h.generate_manifest(candidate)
    elif fault == 'name':
        asset.rename(candidate / asset.name.replace('0.4', '0.3'))
        h.generate_manifest(candidate)
    elif fault in {'sha', 'run', 'attempt'}:
        data = json.loads(h.sidecar(asset, '.provenance.json').read_text())
        data[{'sha': 'source_sha', 'run': 'run_id', 'attempt': 'run_attempt'}[fault]] = 'wrong'
        h.sidecar(asset, '.provenance.json').write_text(json.dumps(data))
    elif fault == 'receipt':
        h.sidecar(asset, '.smoke.json').unlink()
    elif fault == 'version':
        _tar(asset, [('app-cli/VERSION', tarfile.REGTYPE, 'wrong')])
        h.generate_manifest(candidate)
        h.write_provenance(asset, PROVENANCE, 'linux-x64')
        h.write_smoke_receipt(asset, PROVENANCE, 'linux-x64', '0.4', 'Usage: app-cli scan serve')
    else:
        (candidate / 'extra.zip').write_bytes(b'extra')
        h.generate_manifest(candidate)
    assert not h.verify_candidate_set(candidate, PROVENANCE)[0]
    assert not h.create_verified_candidate(candidate, PROVENANCE, tmp_path / 'verified')[0]
    assert not (tmp_path / 'verified').exists()


def test_checksum_wrapper_uses_bash32_compatible_entry(tmp_path):
    (tmp_path / 'a.zip').write_bytes(b'a')
    wrapper = SCRIPT.parent / 'generate-checksums.sh'
    for args in [[], ['--verify']]:
        result = subprocess.run(
            ['/bin/bash', str(wrapper), str(tmp_path), *args], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    (tmp_path / 'MANIFEST.SHA256').write_text('')
    assert (
        subprocess.run(
            ['/bin/bash', str(wrapper), str(tmp_path), '--verify'], capture_output=True
        ).returncode
        != 0
    )


def test_cli_corrupt_archive_fails(tmp_path):
    archive = tmp_path / 'bad.zip'
    archive.write_bytes(b'bad')
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            'verify-archive',
            '--archive',
            str(archive),
            '--platform',
            'linux-x64',
            '--version',
            '0.4',
            '--source-sha',
            PROVENANCE.source_sha,
            '--run-id',
            '100',
            '--run-attempt',
            '1',
        ],
        capture_output=True,
    )
    assert result.returncode != 0


def test_package_launcher_sees_no_external_java(tmp_path, monkeypatch):
    package = _model_runtime(tmp_path)
    java = package / 'runtime/bin/java'
    java.write_text(
        '#!/bin/sh\nif [ -n "${JAVA_HOME:-}${JDK_HOME:-}${JRE_HOME:-}${JAVA_TOOL_OPTIONS:-}${_JAVA_OPTIONS:-}${JDK_JAVA_OPTIONS:-}${CLASSPATH:-}" ]; then exit 88; fi\nif java --version >/dev/null 2>&1; then exit 89; fi\ncase "$1" in --version) echo 0.4;; --help) echo "Usage: app-cli scan serve";; esac\n'
    )
    launcher = package / 'bin/run'
    launcher.write_text(
        '#!/bin/sh\nROOT="$(dirname "$(dirname "$0")")"\nexec "$ROOT/runtime/bin/java" "$@"\n'
    )
    for name in [
        'JAVA_HOME',
        'JDK_HOME',
        'JRE_HOME',
        'JAVA_TOOL_OPTIONS',
        '_JAVA_OPTIONS',
        'JDK_JAVA_OPTIONS',
        'CLASSPATH',
    ]:
        monkeypatch.setenv(name, 'poison')
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert result.success, result.error


@pytest.mark.parametrize('kind', [stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK])
def test_zip_special_types_rejected(tmp_path, kind):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        info = zipfile.ZipInfo('special')
        info.create_system = 3
        info.external_attr = (kind | 0o600) << 16
        output.writestr(info, 'bad')
    assert not h.safe_extract_zip(archive, tmp_path / 'out')[0]


@pytest.mark.parametrize('fault', ['nonobject', 'extra', 'duplicate', 'wrong-size-type'])
def test_candidate_strict_metadata(tmp_path, fault):
    candidate = _candidate(tmp_path / 'candidate')
    archive = candidate / h.archive_name(PROVENANCE, 'generic')
    metadata = h.sidecar(archive, '.provenance.json')
    data = metadata.read_text()
    if fault == 'nonobject':
        data = '[]'
    elif fault == 'duplicate':
        data = data.replace('{', '{"version":"0.4",', 1)
    else:
        values = json.loads(data)
        if fault == 'extra':
            values['extra'] = 'not allowed'
        else:
            values['size'] = str(values['size'])
        data = json.dumps(values)
    metadata.write_text(data)
    assert not h.verify_candidate_set(candidate, PROVENANCE)[0]


def test_candidate_group_manifests_verified_before_copy(tmp_path):
    flat = _candidate(tmp_path / 'flat')
    groups = tmp_path / 'groups'
    groups.mkdir()
    for platform in h.NATIVE_PLATFORMS | {'generic'}:
        group = groups / ('dist-' + platform)
        group.mkdir()
        archive = flat / h.archive_name(PROVENANCE, platform)
        for source in flat.glob(archive.name + '*'):
            source.rename(group / source.name)
        h.generate_manifest(group)
    assert h.verify_candidate_set(groups, PROVENANCE)[0]
    (groups / 'dist-linux-x64/MANIFEST.SHA256').write_text('invalid')
    assert not h.create_verified_candidate(groups, PROVENANCE, tmp_path / 'verified')[0]
    assert not (tmp_path / 'verified').exists()


def test_smoke_rejects_unexecutable_archive_and_removes_stale_receipt(tmp_path):
    candidate = _candidate(tmp_path / 'candidate')
    platform = h.host_platform()
    asset = candidate / h.archive_name(PROVENANCE, platform)
    asset.write_bytes(b'corrupt')
    h.generate_manifest(candidate)
    h.write_provenance(asset, PROVENANCE, platform)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            'verify-archive',
            '--archive',
            str(asset),
            '--platform',
            platform,
            '--version',
            '0.4',
            '--source-sha',
            PROVENANCE.source_sha,
            '--run-id',
            '100',
            '--run-attempt',
            '1',
        ],
        capture_output=True,
    )
    assert result.returncode == 11
    assert not h.sidecar(asset, '.smoke.json').exists()


def test_prepare_uses_real_gradle_tgz_name(tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    platform = h.host_platform()
    _tar(
        raw / 'app-cli-runtime-0.4.tgz',
        [
            ('app-cli/VERSION', tarfile.REGTYPE, '0.4'),
            ('app-cli/bin/run', tarfile.REGTYPE, 'model'),
            ('app-cli/runtime/bin/java', tarfile.REGTYPE, 'model'),
            ('app-cli/app/lib/model.jar', tarfile.REGTYPE, 'model'),
        ],
    )
    output = tmp_path / 'prepared'
    asset = h.prepare_platform_artifact(raw, output, platform, PROVENANCE)
    assert asset.name == h.archive_name(PROVENANCE, platform)
    assert h.verify_manifest_against_files(output / 'MANIFEST.SHA256', output)[0]
    assert not h.sidecar(asset, '.smoke.json').exists()


def test_generic_prepare_is_linux_only(tmp_path, monkeypatch):
    monkeypatch.setattr(h, 'host_platform', lambda: 'macos-arm64')
    with pytest.raises(ValueError, match='linux-x64'):
        h.prepare_platform_artifact(tmp_path, tmp_path / 'prepared', 'generic', PROVENANCE)


def test_drill_does_not_accept_corrupt_packages(tmp_path):
    candidate = tmp_path / 'candidate'
    candidate.mkdir()
    for platform in h.NATIVE_PLATFORMS:
        group = candidate / ('dist-' + platform)
        group.mkdir()
        (group / 'corrupt.zip').write_bytes(b'bad')
    result = subprocess.run(
        [
            '/bin/bash',
            str(SCRIPT.parent / 'drill-upgrade-rollback.sh'),
            '--candidate-dir',
            str(candidate),
            '--version',
            '0.4',
            '--source-sha',
            PROVENANCE.source_sha,
            '--run-id',
            '100',
            '--run-attempt',
            '1',
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 14
    assert 'PASS' not in result.stdout


@pytest.mark.parametrize('name', ['foo.', 'foo ', 'CON', 'nul.txt', 'COM1/log', 'name\nfile'])
def test_cross_platform_path_aliases_rejected(tmp_path, name):
    archive = tmp_path / 'bad.tar.gz'
    _tar(archive, [(name, tarfile.REGTYPE, 'bad')])
    assert not h.safe_extract_tar(archive, tmp_path / 'out')[0]


def test_launcher_nonexecutable_is_not_repaired(tmp_path):
    package = _model_runtime(tmp_path)
    (package / 'bin/run').chmod(0o644)
    result = h.run_launcher_smoke_test(tmp_path, h.host_platform(), '0.4')
    assert not result.success
    assert 'not executable' in result.error
    assert (package / 'bin/run').stat().st_mode & 0o111 == 0


def test_sealing_checks_five_staged_archives_once(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path / 'candidate')
    inspected = []
    inspect = h._inspect

    def record(path, platform, version):
        inspected.append(path)
        inspect(path, platform, version)

    monkeypatch.setattr(h, '_inspect', record)
    success, errors, _ = h.create_verified_candidate(candidate, PROVENANCE)
    assert success, errors
    assert len(inspected) == 5
    assert all(path.parent != candidate for path in inspected)


def test_wrong_identity_preflights_before_reading_archives(tmp_path, monkeypatch):
    candidate = _candidate(tmp_path / 'candidate')

    def unexpected_read(_):
        pytest.fail('wrong identity must be rejected before reading any archive')

    monkeypatch.setattr(h, 'compute_sha256', unexpected_read)
    expected = h.Provenance('0.4', 'b' * 40, '100', '1')
    assert not h.create_verified_candidate(candidate, expected)[0]


def test_combined_prepare_smoke_publishes_only_after_real_launcher_success(tmp_path):
    raw = tmp_path / 'raw'
    raw.mkdir()
    package = raw / 'app-cli-runtime-0.4.tgz'
    output = tmp_path / 'prepared'
    for launcher in (
        '#!/bin/sh\nexit 3\n',
        '#!/bin/sh\ncase "$1" in\n--version) echo 0.4;;\n--help) echo "Usage: app-cli scan serve";;\n*) exit 1;;\nesac\n',
    ):
        _tar(
            package,
            [
                ('app-cli/VERSION', tarfile.REGTYPE, '0.4'),
                ('app-cli/bin/run', tarfile.REGTYPE, launcher),
                ('app-cli/runtime/bin/java', tarfile.REGTYPE, 'model'),
                ('app-cli/app/lib/model.jar', tarfile.REGTYPE, 'model'),
            ],
        )
        if 'exit 3' in launcher:
            with pytest.raises(ValueError, match='launcher --version failed'):
                h.prepare_platform_artifact(raw, output, h.host_platform(), PROVENANCE, smoke=True)
            assert not output.exists()
        else:
            asset = h.prepare_platform_artifact(
                raw, output, h.host_platform(), PROVENANCE, smoke=True
            )
            assert (
                json.loads(h.sidecar(asset, '.smoke.json').read_text())['version_output'] == '0.4'
            )
            assert h.verify_manifest_against_files(output / 'MANIFEST.SHA256', output)[0]
    assert package.is_file()


@pytest.mark.parametrize('fault', ['archive-change', 'sidecar-change', 'interrupted-copy'])
def test_sealing_does_not_publish_if_transfer_changes_input(tmp_path, monkeypatch, fault):
    candidate = _candidate(tmp_path / 'candidate')
    transfer = h._copy_and_measure
    output = tmp_path / 'verified'

    def change_during_transfer(source, target):
        if fault == 'archive-change':
            data = source.read_bytes()
            source.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        elif fault == 'sidecar-change':
            h.sidecar(source, '.provenance.json').write_text('{}')
        else:
            target.write_bytes(b'partial')
            raise OSError('injected interrupted copy')
        return transfer(source, target)

    monkeypatch.setattr(h, '_copy_and_measure', change_during_transfer)
    success, errors, result = h.create_verified_candidate(candidate, PROVENANCE, output)
    assert not success and errors and result is None
    assert not output.exists()
    assert not list(tmp_path.glob('release-verified-*'))


def test_consistent_declarations_do_not_admit_unsafe_archive(tmp_path):
    candidate = _candidate(tmp_path / 'candidate')
    asset = candidate / h.archive_name(PROVENANCE, 'linux-x64')
    _tar(asset, [('../escaped', tarfile.REGTYPE, 'bad')])
    h.generate_manifest(candidate)
    h.write_provenance(asset, PROVENANCE, 'linux-x64')
    h.write_smoke_receipt(asset, PROVENANCE, 'linux-x64', '0.4', 'Usage: app-cli scan serve')
    success, errors, output = h.create_verified_candidate(candidate, PROVENANCE)
    assert not success and 'path traversal' in errors[0] and output is None
    assert not (tmp_path / 'verified-candidate').exists()
    assert not list(tmp_path.glob('release-verified-*'))


def test_prepare_does_not_seal_bytes_changed_after_safety_check(tmp_path, monkeypatch):
    raw = tmp_path / 'raw'
    raw.mkdir()
    package = raw / 'app-cli-runtime-0.4.tgz'
    _tar(
        package,
        [
            ('app-cli/VERSION', tarfile.REGTYPE, '0.4'),
            ('app-cli/bin/run', tarfile.REGTYPE, 'model'),
            ('app-cli/runtime/bin/java', tarfile.REGTYPE, 'model'),
            ('app-cli/app/lib/model.jar', tarfile.REGTYPE, 'model'),
        ],
    )
    original = package.read_bytes()
    inspect = h._inspect

    def replace_source_after_inspection(*args, **kwargs):
        inspect(*args, **kwargs)
        _tar(package, [('../escaped', tarfile.REGTYPE, 'bad')])

    monkeypatch.setattr(h, '_inspect', replace_source_after_inspection)
    output = h.prepare_platform_artifact(raw, tmp_path / 'prepared', 'macos-arm64', PROVENANCE)
    assert output.read_bytes() == original
