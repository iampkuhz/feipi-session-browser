#!/usr/bin/env python3
"""发布工程归档验收工具。

职责：准备唯一资产、严格校验清单、安全解包、运行本机启动器及汇总五包。
不负责产品构建、Git 或发布操作，不证明跨版本迁移能力。
入口：命令行子命令；仅供开发与发布环境使用，不进入产品运行链。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as system_platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

NATIVE_PLATFORMS = frozenset({'macos-arm64', 'macos-x64', 'linux-x64', 'windows-x64'})
VERSION_PATTERN = re.compile(
    r'(?:[0-9]+\.[0-9]+(?:-[A-Za-z0-9._-]+)?|[0-9]+\.[0-9]+\.[0-9]+(?:[.-][A-Za-z0-9._-]+)?)'
)
ASSET_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\.(?:tar\.gz|zip)')


@dataclass(frozen=True)
class Provenance:
    """绑定外部提供的版本、源码与本次运行身份。"""

    version: str
    source_sha: str
    run_id: str
    run_attempt: str

    def to_dict(self):
        """输出可比较的来源字段，不推导可信预期值。"""
        return asdict(self)

    def validate(self):
        """拒绝非法身份，防止身份字段改变路径。"""
        if not VERSION_PATTERN.fullmatch(self.version):
            raise ValueError('invalid version')
        if not re.fullmatch(r'[0-9a-f]{40}', self.source_sha):
            raise ValueError('source SHA must be 40 lowercase hexadecimal characters')
        if not all(
            re.fullmatch(r'[1-9][0-9]*', value) for value in (self.run_id, self.run_attempt)
        ):
            raise ValueError('invalid run identity')


@dataclass(frozen=True)
class ManifestEntry:
    """保存清单中的摘要、大小及唯一文件名。"""

    sha256: str
    size: int
    filename: str


@dataclass
class VerificationResult:
    """记录本次实际启动器验证结果，不表示其他平台已执行。"""

    success: bool
    platform: str
    archive_path: str
    error: str | None = None
    version_in_archive: str | None = None
    launcher_version_output: str | None = None
    launcher_help_output: str | None = None


def compute_sha256(path: Path):
    """流式计算文件摘要。"""
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _regular(path):
    return path.is_file() and not path.is_symlink()


def _archives(directory):
    return sorted(p for p in directory.iterdir() if p.name.endswith(('.zip', '.tar.gz')))


def parse_manifest(path: Path):
    """严格解析非空清单，拒绝重复及不安全文件名。"""
    if not _regular(path):
        return [], 'manifest missing or not a regular file'
    entries = []
    seen = set()
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            match = re.fullmatch(r'([a-fA-F0-9]{64})  ([0-9]+)  ([A-Za-z0-9._-]+)', line)
            if not match:
                raise ValueError('invalid manifest syntax')
            digest, size, name = match.groups()
            if not ASSET_PATTERN.fullmatch(name) or '..' in name:
                raise ValueError('unsafe filename')
            if name.casefold() in seen:
                raise ValueError('duplicate filename')
            seen.add(name.casefold())
            entries.append(ManifestEntry(digest.lower(), int(size), name))
        if not entries:
            raise ValueError('manifest is empty')
        return entries, None
    except (OSError, UnicodeError, ValueError) as error:
        return [], str(error)


def verify_manifest_against_files(manifest_path: Path, dist_dir: Path):
    """验证清单与实际归档一一对应，拒绝目录及链接伪装。"""
    entries, error = parse_manifest(manifest_path)
    if error:
        return False, [error]
    errors = []
    if {p.name for p in _archives(dist_dir)} != {e.filename for e in entries}:
        errors.append('manifest/archive membership mismatch')
    for entry in entries:
        asset = dist_dir / entry.filename
        if not _regular(asset):
            errors.append(f'missing file or nonregular asset: {entry.filename}')
        elif asset.stat().st_size != entry.size:
            errors.append(f'size mismatch: {entry.filename}')
        elif compute_sha256(asset) != entry.sha256:
            errors.append(f'hash mismatch: {entry.filename}')
    return not errors, errors


def generate_manifest(directory: Path):
    """为非空正规归档集合生成清单；不用于认可下载输入。"""
    assets = _archives(directory)
    if not assets or any(
        not _regular(p) or not ASSET_PATTERN.fullmatch(p.name) or '..' in p.name for p in assets
    ):
        raise ValueError('empty or unsafe archive set')
    (directory / 'MANIFEST.SHA256').write_text(
        ''.join(f'{compute_sha256(p)}  {p.stat().st_size}  {p.name}\n' for p in assets),
        encoding='utf-8',
    )


def _safe_path(name):
    if not name or '\\' in name or ':' in name or name.startswith('/'):
        raise ValueError(f'absolute or windows path: {name}')
    if '..' in name.split('/'):
        raise ValueError(f'path traversal: {name}')
    path = PurePosixPath(name)
    if str(path) == '.':
        raise ValueError('empty target')
    reserved = {'con', 'prn', 'aux', 'nul'} | {
        f'{prefix}{n}' for prefix in ('com', 'lpt') for n in range(1, 10)
    }
    if any(
        part.endswith(('.', ' '))
        or any(ord(character) < 32 for character in part)
        or part.split('.')[0].casefold() in reserved
        for part in path.parts
    ):
        raise ValueError(f'ambiguous Windows target: {name}')
    return path


def _validate_entries(entries):
    seen = {}
    for name, kind in entries:
        path = _safe_path(name)
        key = str(path).casefold()
        if key in seen:
            raise ValueError(f'duplicate target: {name}')
        if kind not in {'file', 'directory'}:
            raise ValueError(f'links and special files not allowed: {name}')
        seen[key] = kind
    for key in seen:
        if any(seen.get(str(parent)) == 'file' for parent in PurePosixPath(key).parents):
            raise ValueError(f'file used as directory: {key}')


def _extract(archive_path, destination, fmt):
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        return False, 'extraction destination must be empty and not a symlink'
    try:
        if fmt == 'tar':
            with tarfile.open(archive_path, 'r:*') as archive:
                members = archive.getmembers()
                _validate_entries(
                    [
                        (m.name, 'directory' if m.isdir() else 'file' if m.isreg() else 'forbidden')
                        for m in members
                    ]
                )
                destination.mkdir(parents=True, exist_ok=True)
                for member in members:
                    target = destination / str(_safe_path(member.name))
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        source = archive.extractfile(member)
                        if source is None:
                            raise ValueError('missing tar content')
                        with source, target.open('xb') as output:
                            shutil.copyfileobj(source, output)
                        target.chmod(member.mode & 0o777)
        else:
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                entries = []
                for member in members:
                    mode = member.external_attr >> 16
                    file_type = stat.S_IFMT(mode)
                    kind = 'directory' if member.is_dir() else 'file'
                    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR} or (
                        file_type == stat.S_IFDIR and not member.is_dir()
                    ):
                        kind = 'forbidden'
                    entries.append((member.filename, kind))
                _validate_entries(entries)
                destination.mkdir(parents=True, exist_ok=True)
                for member in members:
                    target = destination / str(_safe_path(member.filename))
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open('xb') as output:
                            shutil.copyfileobj(source, output)
                        mode = (member.external_attr >> 16) & 0o777
                        if mode:
                            target.chmod(mode)
        return True, None
    except (
        OSError,
        ValueError,
        EOFError,
        tarfile.TarError,
        zipfile.BadZipFile,
        RuntimeError,
    ) as error:
        return False, f'extraction failed: {error}'


def safe_extract_tar(path: Path, destination: Path):
    """先检查全部条目再手工解包；明确拒绝所有链接及特殊文件。"""
    return _extract(path, destination, 'tar')


def safe_extract_zip(path: Path, destination: Path):
    """先检查全部条目再手工解包，并保留启动文件权限。"""
    return _extract(path, destination, 'zip')


def host_platform():
    """识别当前宿主，防止异平台验证被记为实际启动。"""
    system = {'Darwin': 'macos', 'Linux': 'linux', 'Windows': 'windows'}.get(
        system_platform.system(), 'unknown'
    )
    arch = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}.get(
        system_platform.machine().lower(), 'unknown'
    )
    return f'{system}-{arch}'


def _package_root(extracted, platform):
    expected = 'app-cli' if platform in NATIVE_PLATFORMS else None
    roots = list(extracted.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or (expected and roots[0].name != expected):
        raise ValueError('archive must contain exactly one package root')
    return roots[0]


def _structure(extracted, platform, version):
    root = _package_root(extracted, platform)
    version_file = root / 'VERSION'
    if not _regular(version_file):
        raise ValueError('VERSION file not found')
    if version_file.read_text(encoding='utf-8').strip() != version:
        raise ValueError('VERSION mismatch')
    if platform == 'generic':
        jars = list((root / 'lib').glob('*.jar'))
        if root.name != f'app-cli-{version}' or not jars or any(not _regular(jar) for jar in jars):
            raise ValueError('invalid generic layout')
    else:
        windows = platform == 'windows-x64'
        for relative in [
            'bin/run.bat' if windows else 'bin/run',
            'runtime/bin/java.exe' if windows else 'runtime/bin/java',
        ]:
            if not _regular(root / relative):
                raise ValueError(f'missing launcher/runtime: {relative}')
            if not windows and not (root / relative).stat().st_mode & 0o111:
                raise ValueError(f'launcher/runtime not executable: {relative}')
        jars = list((root / 'app/lib').glob('*.jar'))
        if not jars or any(not _regular(jar) for jar in jars):
            raise ValueError('app/lib jars missing or not regular files')
    return root


def _valid_outputs(version_output, help_output, version):
    version_output = re.sub(r'\x1b\[[0-9;]*m', '', version_output)
    help_output = re.sub(r'\x1b\[[0-9;]*m', '', help_output)
    return (
        bool(re.search(rf'(?<![\w.]){re.escape(version)}(?![\w.-])', version_output))
        and 'Usage:' in help_output
        and all(command in help_output.split() for command in ('scan', 'serve'))
    )


def run_launcher_smoke_test(
    extract_dir: Path, platform: str, expected_version: str, isolate_env=True
):
    """隔离系统 Java 后执行包内启动器；不直接调用 Java 绕过启动入口。"""
    result = VerificationResult(False, platform, str(extract_dir))
    try:
        root = _structure(extract_dir, platform, expected_version).resolve()
        result.version_in_archive = expected_version
        if platform != host_platform() or not isolate_env:
            raise ValueError('native smoke requires matching host and isolated environment')
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            not in {
                'JAVA_HOME',
                'JDK_HOME',
                'JRE_HOME',
                'JAVA_TOOL_OPTIONS',
                '_JAVA_OPTIONS',
                'JDK_JAVA_OPTIONS',
                'CLASSPATH',
                'PATH',
            }
        }
        with tempfile.TemporaryDirectory(prefix='release-tools-') as directory:
            tools = Path(directory)
            if os.name != 'nt':
                dirname = shutil.which('dirname', path='/usr/bin:/bin')
                if not dirname:
                    raise ValueError('system dirname unavailable')
                (tools / 'dirname').symlink_to(dirname)
                blocker = tools / 'java'
                blocker.write_text('#!/bin/sh\nexit 97\n', encoding='utf-8')
                blocker.chmod(0o755)
            env['PATH'] = str(tools)
            launcher = root / 'bin' / ('run.bat' if os.name == 'nt' else 'run')
            command = [str(launcher)]
            if os.name == 'nt':
                command = [
                    str(Path(os.environ['SystemRoot']) / 'System32/cmd.exe'),
                    '/d',
                    '/c',
                    str(launcher),
                ]
            outputs = []
            for argument in ('--version', '--help'):
                completed = subprocess.run(
                    [*command, argument],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    timeout=60,
                    check=False,
                )
                # JDK 管道输出按 UTF-8 严格解码，不依赖 Windows ANSI locale。
                stdout = completed.stdout.decode('utf-8')
                stderr = completed.stderr.decode('utf-8')
                if completed.returncode:
                    raise ValueError(
                        f'launcher {argument} failed: returncode={completed.returncode}, '
                        f'stdout_chars={len(stdout)}, stderr_chars={len(stderr)}'
                    )
                outputs.append(stdout.strip())
            if not _valid_outputs(*outputs, expected_version):
                diagnostics = {
                    'version_chars': len(outputs[0]),
                    'help_chars': len(outputs[1]),
                    'version_sgr': len(re.findall(r'\x1b\[[0-9;]*m', outputs[0])),
                    'help_sgr': len(re.findall(r'\x1b\[[0-9;]*m', outputs[1])),
                    'version_matches': _valid_outputs(
                        outputs[0], 'Usage: scan serve', expected_version
                    ),
                    'help_matches': _valid_outputs(expected_version, outputs[1], expected_version),
                }
                raise ValueError(f'launcher version/help output mismatch: {diagnostics}')
            result.launcher_version_output, result.launcher_help_output = outputs
            result.success = True
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result.error = str(error)
    return result


def archive_name(provenance: Provenance, platform: str):
    """生成携带版本和平台的固定资产名；来源由旁车严格绑定。"""
    provenance.validate()
    if platform not in NATIVE_PLATFORMS | {'generic'}:
        raise ValueError('unexpected platform')
    if platform == 'generic':
        return f'app-cli-{provenance.version}-generic.zip'
    suffix = 'zip' if platform == 'windows-x64' else 'tar.gz'
    return f'app-cli-{provenance.version}-runtime-{platform}.{suffix}'


def sidecar(archive: Path, suffix: str):
    """在完整资产名之后追加元数据后缀。"""
    return archive.with_name(archive.name + suffix)


def _identity(archive, provenance, platform):
    return {
        **provenance.to_dict(),
        'platform': platform,
        'producer_platform': 'linux-x64' if platform == 'generic' else platform,
        'filename': archive.name,
        'sha256': compute_sha256(archive),
        'size': archive.stat().st_size,
    }


def write_provenance(archive: Path, provenance: Provenance, platform: str):
    """为准备后的资产写入来源与内容身份。"""
    sidecar(archive, '.provenance.json').write_text(
        json.dumps(_identity(archive, provenance, platform), sort_keys=True) + '\n',
        encoding='utf-8',
    )


def write_smoke_receipt(
    archive: Path, provenance: Provenance, platform: str, version_output: str, help_output: str
):
    """记录已执行的原生验证输出；调用方必须先完成真实启动。"""
    data = {
        **_identity(archive, provenance, platform),
        'host_platform': platform,
        'version_output': version_output,
        'help_output': help_output,
    }
    sidecar(archive, '.smoke.json').write_text(
        json.dumps(data, sort_keys=True) + '\n', encoding='utf-8'
    )


def _read_json(path):
    if not _regular(path):
        raise ValueError(f'missing or nonregular metadata: {path.name}')

    def unique(pairs):
        """拒绝重复字段，避免来源元数据被静默覆盖。"""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError('metadata must be an object')
    return data


def _check_metadata(archive, provenance, platform, smoke=False):
    suffix = '.smoke.json' if smoke else '.provenance.json'
    data = _read_json(sidecar(archive, suffix))
    expected = _identity(archive, provenance, platform)
    if smoke:
        expected.update(
            host_platform=platform,
            version_output=data.get('version_output'),
            help_output=data.get('help_output'),
        )
        if (
            not isinstance(data.get('version_output'), str)
            or not isinstance(data.get('help_output'), str)
            or not _valid_outputs(data['version_output'], data['help_output'], provenance.version)
        ):
            raise ValueError('invalid smoke outputs')
    if data != expected or any(
        type(data[key]) is not type(value) for key, value in expected.items()
    ):
        raise ValueError(f'provenance/receipt mismatch: {archive.name}')


def _inspect(archive, platform, version):
    with tempfile.TemporaryDirectory(prefix='release-inspect-') as temporary:
        destination = Path(temporary) / 'package'
        success, error = (safe_extract_zip if archive.name.endswith('.zip') else safe_extract_tar)(
            archive, destination
        )
        if not success:
            raise ValueError(error)
        _structure(destination, platform, version)


def prepare_platform_artifact(
    dist_dir: Path, output_dir: Path, platform: str, provenance: Provenance
):
    """从明确的构建目录选唯一资产，安全检查后输出独立平台目录。"""
    provenance.validate()
    if platform == 'generic' and host_platform() != 'linux-x64':
        raise ValueError('generic must be prepared on linux-x64')
    source_name = (
        f'app-cli-{provenance.version}.zip'
        if platform == 'generic'
        else f'app-cli-runtime-{provenance.version}.'
        + ('zip' if platform == 'windows-x64' else 'tgz')
    )
    source = dist_dir / source_name
    if not _regular(source):
        raise ValueError(f'expected build archive missing: {source_name}')
    if output_dir.exists():
        raise ValueError('output directory already exists')
    _inspect(source, platform, provenance.version)
    output_dir.mkdir(parents=True)
    target = output_dir / archive_name(provenance, platform)
    shutil.copyfile(source, target)
    write_provenance(target, provenance, platform)
    generate_manifest(output_dir)
    return target


def _candidate_assets(candidate, provenance):
    provenance.validate()
    if not candidate.is_dir() or candidate.is_symlink():
        raise ValueError('candidate directory missing or symlink')
    groups = (
        [candidate] if (candidate / 'MANIFEST.SHA256').exists() else sorted(candidate.iterdir())
    )
    if not groups or any(not p.is_dir() or p.is_symlink() for p in groups):
        raise ValueError('candidate requires flat manifest or one level of platform directories')
    assets = {}
    for group in groups:
        valid, errors = verify_manifest_against_files(group / 'MANIFEST.SHA256', group)
        if not valid:
            raise ValueError('; '.join(errors))
        allowed = {'MANIFEST.SHA256'}
        for archive in _archives(group):
            platforms = [
                p
                for p in NATIVE_PLATFORMS | {'generic'}
                if archive.name == archive_name(provenance, p)
            ]
            if len(platforms) != 1 or platforms[0] in assets:
                raise ValueError(f'duplicate or unexpected package: {archive.name}')
            platform = platforms[0]
            _check_metadata(archive, provenance, platform)
            _inspect(archive, platform, provenance.version)
            allowed.update({archive.name, archive.name + '.provenance.json'})
            if platform != 'generic':
                _check_metadata(archive, provenance, platform, smoke=True)
                allowed.add(archive.name + '.smoke.json')
            assets[platform] = archive
        if {p.name for p in group.iterdir()} != allowed:
            raise ValueError('unexpected or missing candidate metadata')
    if set(assets) != NATIVE_PLATFORMS | {'generic'}:
        raise ValueError('missing native platform or unique generic package')
    return assets


def verify_candidate_set(candidate_dir: Path, expected: Provenance):
    """在汇总边界复核输入清单、归档及四个原生验证凭据。"""
    try:
        assets = _candidate_assets(candidate_dir, expected)
        return (
            True,
            [],
            {
                'native_platforms': sorted(NATIVE_PLATFORMS),
                'generic': 'generic',
                'total_packages': len(assets),
            },
        )
    except (ValueError, OSError, UnicodeError, TypeError) as error:
        return False, [str(error)], {}


def create_verified_candidate(
    candidate_dir: Path, expected: Provenance, output_dir: Path | None = None
):
    """先验输入再复制五包，最后重验输出；失败不留下可发布目录。"""
    output_dir = output_dir or candidate_dir.parent / 'verified-candidate'
    try:
        assets = _candidate_assets(candidate_dir, expected)
        if output_dir.exists() or output_dir.is_symlink():
            raise ValueError('output already exists')
        with tempfile.TemporaryDirectory(
            prefix='release-verified-', dir=output_dir.parent
        ) as temporary:
            staging = Path(temporary) / 'candidate'
            staging.mkdir()
            for platform, archive in assets.items():
                for source in [
                    archive,
                    sidecar(archive, '.provenance.json'),
                    *([sidecar(archive, '.smoke.json')] if platform != 'generic' else []),
                ]:
                    shutil.copyfile(source, staging / source.name)
            generate_manifest(staging)
            _candidate_assets(staging, expected)
            staging.rename(output_dir)
        return True, [], output_dir
    except (ValueError, OSError, UnicodeError, TypeError) as error:
        return False, [str(error)], None


def main():
    """解析命令并返回稳定退出码；验证命令不执行任何发布操作。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    checksum = commands.add_parser('checksums')
    checksum.add_argument('--dist-dir', type=Path, required=True)
    checksum.add_argument('--verify', action='store_true')
    for name in ['prepare', 'verify-archive', 'verify-candidate', 'create-verified']:
        command = commands.add_parser(name)
        for field in ['version', 'source-sha', 'run-id', 'run-attempt']:
            command.add_argument('--' + field, required=True)
        if name in {'prepare', 'verify-archive'}:
            command.add_argument(
                '--platform',
                choices=sorted(NATIVE_PLATFORMS | ({'generic'} if name == 'prepare' else set())),
                required=True,
            )
        if name == 'prepare':
            command.add_argument('--dist-dir', type=Path, required=True)
            command.add_argument('--output-dir', type=Path, required=True)
        elif name == 'verify-archive':
            command.add_argument('--archive', type=Path, required=True)
        else:
            command.add_argument('--candidate-dir', type=Path, required=True)
            if name == 'create-verified':
                command.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'checksums':
            if args.verify:
                valid, errors = verify_manifest_against_files(
                    args.dist_dir / 'MANIFEST.SHA256', args.dist_dir
                )
                if not valid:
                    raise ValueError('; '.join(errors))
            else:
                generate_manifest(args.dist_dir)
            return 0
        provenance = Provenance(args.version, args.source_sha, args.run_id, args.run_attempt)
        provenance.validate()
        if args.command == 'prepare':
            print(
                prepare_platform_artifact(args.dist_dir, args.output_dir, args.platform, provenance)
            )
        elif args.command == 'verify-archive':
            if not _regular(args.archive):
                raise ValueError('archive must be a regular file, not symlink')
            archive = args.archive.resolve()
            sidecar(archive, '.smoke.json').unlink(missing_ok=True)
            if archive.name != archive_name(provenance, args.platform):
                raise ValueError('archive name mismatch')
            valid, errors = verify_manifest_against_files(
                archive.parent / 'MANIFEST.SHA256', archive.parent
            )
            if not valid:
                raise ValueError('; '.join(errors))
            _check_metadata(archive, provenance, args.platform)
            with tempfile.TemporaryDirectory(prefix='release-smoke-') as temporary:
                destination = Path(temporary) / 'package'
                valid, error = (
                    safe_extract_zip if archive.name.endswith('.zip') else safe_extract_tar
                )(archive, destination)
                if not valid:
                    print(error, file=sys.stderr)
                    return 11
                result = run_launcher_smoke_test(destination, args.platform, args.version)
                if not result.success:
                    print(result.error, file=sys.stderr)
                    return 13
                write_smoke_receipt(
                    archive,
                    provenance,
                    args.platform,
                    result.launcher_version_output,
                    result.launcher_help_output,
                )
                print(json.dumps(asdict(result)))
        elif args.command == 'verify-candidate':
            valid, errors, summary = verify_candidate_set(args.candidate_dir, provenance)
            if not valid:
                raise ValueError('; '.join(errors))
            print(json.dumps(summary))
        else:
            valid, errors, output = create_verified_candidate(
                args.candidate_dir, provenance, args.output_dir
            )
            if not valid:
                raise ValueError('; '.join(errors))
            print(output)
        return 0
    except (OSError, ValueError, UnicodeError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return {
            'checksums': 10,
            'prepare': 1,
            'verify-archive': 15,
            'verify-candidate': 14,
            'create-verified': 14,
        }[args.command]


if __name__ == '__main__':
    sys.exit(main())
