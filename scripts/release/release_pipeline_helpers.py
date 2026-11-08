#!/usr/bin/env python3
"""发布工程归档验收工具。

职责：准备唯一 macOS arm64 原生包、安全解包、真实启动并验证候选身份。
不负责产品构建、Git 或发布操作，不证明跨版本迁移能力。
入口：命令行子命令；仅供开发与发布环境使用，不进入产品运行链。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform as system_platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

PLATFORM = 'macos-arm64'
VERSION_PATTERN = re.compile(
    r'(?:[0-9]+\.[0-9]+(?:-[A-Za-z0-9._-]+)?|[0-9]+\.[0-9]+\.[0-9]+(?:[.-][A-Za-z0-9._-]+)?)'
)
ASSET_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz')


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
        if not VERSION_PATTERN.fullmatch(self.version) or '..' in self.version:
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
    error: str | None = None
    launcher_version_output: str | None = None
    launcher_help_output: str | None = None
    serve_help_output: str | None = None


def compute_sha256(path: Path):
    """流式计算文件摘要。"""
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _regular(path):
    return path.is_file() and not path.is_symlink()


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


def _measure(archive):
    return ManifestEntry(compute_sha256(archive), archive.stat().st_size, archive.name)


def _write_manifest(directory, entry):
    (directory / 'MANIFEST.SHA256').write_text(
        f'{entry.sha256}  {entry.size}  {entry.filename}\n',
        encoding='utf-8',
    )


def _copy_and_measure(source, target):
    """散列实际写入私有 staging 的字节；不信任输入声明或文件时间。"""
    digest = hashlib.sha256()
    size = 0
    with source.open('rb') as stream, target.open('xb') as output:
        while chunk := stream.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return ManifestEntry(digest.hexdigest(), size, target.name)


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


def safe_extract_tar(path: Path, destination: Path):
    """先验证所有条目再解包，保留可执行权限，不接受链接或特殊文件。"""
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        return False, 'extraction destination must be empty and not a symlink'
    try:
        with tarfile.open(path, 'r:gz') as archive:
            members = archive.getmembers()
            _validate_entries(
                (m.name, 'directory' if m.isdir() else 'file' if m.isreg() else 'forbidden')
                for m in members
            )
            destination.mkdir(parents=True, exist_ok=True)
            for member in members:
                target = destination / _safe_path(member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError('missing tar content')
                with source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
        return True, None
    except (OSError, ValueError, EOFError, tarfile.TarError) as error:
        return False, f'extraction failed: {error}'


def is_macos_arm64():
    """检查真实原生宿主，不把异平台验证记为发行 smoke。"""
    return system_platform.system() == 'Darwin' and system_platform.machine() == 'arm64'


def _structure(extracted, version):
    root = extracted / 'app-cli'
    if list(extracted.iterdir()) != [root] or not root.is_dir():
        raise ValueError('archive must contain exactly one app-cli root')
    version_file = root / 'VERSION'
    if not _regular(version_file) or version_file.read_text(encoding='utf-8').strip() != version:
        raise ValueError('missing or mismatched VERSION')
    for relative in ('bin/run', 'runtime/bin/java'):
        file = root / relative
        if not _regular(file) or not file.stat().st_mode & 0o111:
            raise ValueError(f'missing or non-executable launcher/runtime: {relative}')
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


def _valid_serve_help(output):
    return 'Usage:' in output and '--no-scan' in output and '--index-dir' in output


def _launch(root, args, env):
    completed = subprocess.run(
        [str(root / 'bin/run'), *args],
        cwd=root,
        env=env,
        capture_output=True,
        timeout=60,
        check=False,
    )
    try:
        stdout = completed.stdout.decode('utf-8')
        stderr = completed.stderr.decode('utf-8')
    except UnicodeError as error:
        raise ValueError(f'launcher output is not UTF-8: {args[-1]}') from error
    if completed.returncode:
        raise ValueError(
            f'launcher {args[-1]} failed: returncode={completed.returncode}, '
            f'stdout_chars={len(stdout)}, stderr_chars={len(stderr)}'
        )
    return stdout.strip(), stderr


def run_launcher_smoke_test(extract_dir: Path, version: str):
    """只用归档 launcher，核验 JVM 架构、隔离 home 和无扫描 serve 帮助。"""
    result = VerificationResult(False)
    try:
        if not is_macos_arm64():
            raise ValueError('release smoke requires native macOS arm64')
        root = _structure(extract_dir, version).resolve()
        with tempfile.TemporaryDirectory(prefix='release-tools-') as directory:
            sandbox = Path(directory).resolve()
            home = sandbox / 'home'
            home.mkdir()
            index = sandbox / 'index'
            dirname = shutil.which('dirname', path='/usr/bin:/bin')
            if not dirname:
                raise ValueError('system dirname unavailable')
            (sandbox / 'dirname').symlink_to(dirname)
            blocker = sandbox / 'java'
            blocker.write_text('#!/bin/sh\nexit 97\n', encoding='utf-8')
            blocker.chmod(0o755)
            env = {
                'HOME': str(home),
                'PATH': str(sandbox),
                'JAVA_TOOL_OPTIONS': f'-Duser.home="{home}"',
            }
            version_output, _ = _launch(root, ['--version'], env)
            help_output, _ = _launch(root, ['--help'], env)
            serve_output, properties = _launch(
                root,
                ['serve', '--no-scan', '--index-dir', str(index), '--help'],
                env | {'JDK_JAVA_OPTIONS': '-XshowSettings:properties'},
            )
            if re.findall(r'^\s*user\.home = (.*)$', properties, re.M) != [str(home)]:
                raise ValueError('launcher did not use the isolated JVM home')
            architectures = re.findall(r'^\s*os\.arch = (.*)$', properties, re.M)
            if architectures != ['aarch64']:
                raise ValueError('launcher JVM os.arch must be aarch64')
            if index.exists() or index.is_symlink():
                raise ValueError('serve help unexpectedly created an index')
            if not _valid_outputs(version_output, help_output, version) or not _valid_serve_help(
                serve_output
            ):
                raise ValueError('launcher version/help output mismatch')
            result = VerificationResult(True, None, version_output, help_output, serve_output)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result.error = str(error)
    return result


def archive_name(provenance: Provenance):
    """生成唯一发行资产名；来源由旁车严格绑定。"""
    provenance.validate()
    return f'app-cli-{provenance.version}-runtime-{PLATFORM}.tar.gz'


def sidecar(archive: Path, suffix: str):
    """在完整资产名之后追加元数据后缀。"""
    return archive.with_name(archive.name + suffix)


def _identity(entry, provenance):
    return {
        **provenance.to_dict(),
        'platform': PLATFORM,
        'producer_platform': PLATFORM,
        'filename': entry.filename,
        'sha256': entry.sha256,
        'size': entry.size,
    }


def _write_sidecar(archive, suffix, data):
    sidecar(archive, suffix).write_text(json.dumps(data, sort_keys=True) + '\n', encoding='utf-8')


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


def _check_metadata(archive, entry, provenance, *, smoke=False):
    suffix = '.smoke.json' if smoke else '.provenance.json'
    data = _read_json(sidecar(archive, suffix))
    expected = _identity(entry, provenance)
    if smoke:
        version, help_text, serve_help = (
            data.get(key) for key in ('version_output', 'help_output', 'serve_help_output')
        )
        if (
            not all(isinstance(output, str) for output in (version, help_text, serve_help))
            or not _valid_outputs(version, help_text, provenance.version)
            or not _valid_serve_help(serve_help)
        ):
            raise ValueError('invalid smoke outputs')
        expected.update(
            host_platform=PLATFORM,
            version_output=version,
            help_output=help_text,
            serve_help_output=serve_help,
            isolated_jvm_home=True,
        )
    if data != expected or any(
        type(data[key]) is not type(value) for key, value in expected.items()
    ):
        raise ValueError(f'provenance/receipt mismatch: {archive.name}')


def _inspect(archive, version, *, smoke=False):
    with tempfile.TemporaryDirectory(prefix='release-inspect-') as temporary:
        destination = Path(temporary) / 'package'
        valid, error = safe_extract_tar(archive, destination)
        if not valid:
            raise ValueError(error)
        if not smoke:
            _structure(destination, version)
            return None
        result = run_launcher_smoke_test(destination, version)
        if not result.success:
            raise ValueError(result.error)
        return result


def prepare_candidate(dist_dir: Path, output_dir: Path, provenance: Provenance):
    """仅发布私有 staging 内实际启动且可追溯的唯一归档，不重打包。"""
    filename = archive_name(provenance)
    if not is_macos_arm64():
        raise ValueError('release preparation requires native macOS arm64')
    source = dist_dir / f'app-cli-runtime-{provenance.version}.tgz'
    if not _regular(source):
        raise ValueError(f'expected build archive missing: {source.name}')
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError('output directory already exists')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-prepare-', dir=output_dir.parent) as temporary:
        staging = Path(temporary) / 'candidate'
        staging.mkdir()
        target = staging / filename
        entry = _copy_and_measure(source, target)
        result = _inspect(target, provenance.version, smoke=True)
        identity = _identity(entry, provenance)
        _write_sidecar(target, '.provenance.json', identity)
        _write_sidecar(
            target,
            '.smoke.json',
            {
                **identity,
                'host_platform': PLATFORM,
                'version_output': result.launcher_version_output,
                'help_output': result.launcher_help_output,
                'serve_help_output': result.serve_help_output,
                'isolated_jvm_home': True,
            },
        )
        _write_manifest(staging, entry)
        staging.rename(output_dir)
    return output_dir / filename


def verify_candidate_set(candidate: Path, provenance: Provenance):
    """复核唯一候选的精确文件集合、身份、字节及归档结构，不在异平台运行。"""
    try:
        filename = archive_name(provenance)
        if not candidate.is_dir() or candidate.is_symlink():
            raise ValueError('candidate directory missing or symlink')
        archive = candidate / filename
        manifest = candidate / 'MANIFEST.SHA256'
        expected = {
            archive,
            manifest,
            sidecar(archive, '.provenance.json'),
            sidecar(archive, '.smoke.json'),
        }
        if set(candidate.iterdir()) != expected or not all(_regular(file) for file in expected):
            raise ValueError('unexpected, missing or nonregular candidate file')
        entries, error = parse_manifest(manifest)
        if error or len(entries) != 1 or entries[0].filename != filename:
            raise ValueError(error or 'expected one exact archive in manifest')
        entry = entries[0]
        _check_metadata(archive, entry, provenance)
        _check_metadata(archive, entry, provenance, smoke=True)
        if _measure(archive) != entry:
            raise ValueError(f'size or hash mismatch: {archive.name}')
        _inspect(archive, provenance.version)
        return True, [], {'native_platform': PLATFORM, 'total_packages': 1}
    except (ValueError, OSError, TypeError) as error:
        return False, [str(error)], {}


def main():
    """解析命令并返回退出码；不执行 Git 或远端发布。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--dist-dir', type=Path, required=True)
    prepare.add_argument('--output-dir', type=Path, required=True)
    verify = commands.add_parser('verify-candidate')
    verify.add_argument('--candidate-dir', type=Path, required=True)
    for command in (prepare, verify):
        for field in ('version', 'source-sha', 'run-id', 'run-attempt'):
            command.add_argument('--' + field, required=True)
    args = parser.parse_args()
    try:
        provenance = Provenance(args.version, args.source_sha, args.run_id, args.run_attempt)
        if args.command == 'prepare':
            print(prepare_candidate(args.dist_dir, args.output_dir, provenance))
        else:
            valid, errors, summary = verify_candidate_set(args.candidate_dir, provenance)
            if not valid:
                raise ValueError('; '.join(errors))
            print(json.dumps(summary))
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
