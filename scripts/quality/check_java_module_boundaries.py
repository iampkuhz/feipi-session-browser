#!/usr/bin/env python3
"""检查 Java Gradle module、package、import 与 class placement 边界。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered
DEFAULT_CONFIG = REPO_ROOT / 'config' / 'architecture' / 'java-modules.yaml'

# 触发模式：当变更文件匹配这些 pattern 时才运行检查。
TRIGGER_PATTERNS = [
    'config/architecture/java-modules.yaml',
    'settings.gradle.kts',
    'java/**/build.gradle.kts',
    'java/**/src/main/java/**/*.java',
    '**/*.java',
]


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    path: str
    message: str

    # 格式化为命令行输出文本。
    def format(self) -> str:
        """返回：
            单行检查结果文本。
        """
        return f'{self.level} {self.code} {self.path}: {self.message}'


# 读取模块边界配置。
def load_config(path: Path) -> dict[str, Any]:
    """参数：
        path: 配置文件路径。

    返回：
        配置字典。
    """
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise SystemExit(f'{path}: 当前配置使用 JSON-compatible YAML，请修正语法: {exc}') from exc


# 解析 settings.gradle.kts 中登记的模块。
def parse_settings_includes(settings: Path) -> list[str]:
    """参数：
        settings: Gradle settings 文件路径。

    返回：
        模块路径列表。
    """
    text = settings.read_text(encoding='utf-8')
    includes: list[str] = []
    for match in re.finditer(r'include\((.*?)\)', text, flags=re.DOTALL):
        body = match.group(1)
        includes.extend(':' + item.replace(':', ':') for item in re.findall(r'"([^"]+)"', body))
    return includes


# 根据 Gradle 模块路径获取模块目录。
def module_dir(module_path: str) -> Path:
    """参数：
        module_path: Gradle 模块路径。

    返回：
        模块根目录。
    """
    if module_path == ':app-cli':
        return REPO_ROOT / 'app-cli'
    if module_path.startswith(':'):
        return REPO_ROOT / module_path.strip(':').replace(':', '/')
    return REPO_ROOT / module_path.replace(':', '/')


# 解析 build.gradle.kts 中的 production project 依赖。
def parse_project_deps(build_file: Path) -> list[str]:
    """参数：
        build_file: Gradle 构建文件路径。

    返回：
        production project 依赖列表。
    """
    if not build_file.exists():
        return []
    deps: set[str] = set()
    for line in build_file.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        # 这里只治理 production dependency 方向；测试 fixture 可以更宽松。
        if stripped.startswith((
            'testImplementation',
            'testRuntimeOnly',
            'testCompileOnly',
            'testAnnotationProcessor',
        )):
            continue
        deps.update(re.findall(r'project\("([^"]+)"\)', stripped))
    return sorted(deps)


# 枚举 source root 下的 Java 文件。
def java_files(source_root: Path) -> list[Path]:
    """参数：
        source_root: Java 源码根目录。

    返回：
        Java 文件列表。
    """
    if not source_root.exists():
        return []
    return sorted(p for p in source_root.rglob('*.java') if '/build/' not in p.as_posix())


# 读取 Java 文件的 package 名称。
def package_name(java_file: Path) -> str | None:
    """参数：
        java_file: Java 文件路径。

    返回：
        package 名称；缺失时返回 None。
    """
    for line in java_file.read_text(encoding='utf-8', errors='ignore').splitlines():
        stripped = line.strip()
        if stripped.startswith('package ') and stripped.endswith(';'):
            return stripped.removeprefix('package ').removesuffix(';').strip()
    return None


# 读取 Java 文件 import 列表。
def imports(java_file: Path) -> list[str]:
    """参数：
        java_file: Java 文件路径。

    返回：
        import 名称列表。
    """
    result: list[str] = []
    for line in java_file.read_text(encoding='utf-8', errors='ignore').splitlines():
        stripped = line.strip()
        if stripped.startswith('import ') and stripped.endswith(';'):
            result.append(stripped.removeprefix('import ').removesuffix(';').strip())
    return result


# 转换为仓库相对路径。
def rel(path: Path) -> str:
    """参数：
        path: 待转换路径。

    返回：
        仓库相对路径或原路径。
    """
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# 判断 package 是否匹配允许根。
def package_matches(pkg: str, roots: list[str]) -> bool:
    """参数：
        pkg: Java package 名称。
        roots: 允许的 package 根列表。

    返回：
        是否匹配。
    """
    return any(pkg == root or pkg.startswith(root + '.') for root in roots)


# 检查 Gradle include 与配置登记是否一致。
def check_includes(config: dict[str, Any]) -> list[Finding]:
    """参数：
        config: 模块边界配置。

    返回：
        检查结果列表。
    """
    findings: list[Finding] = []
    configured = set(config['modules'].keys())
    actual = set(parse_settings_includes(REPO_ROOT / 'settings.gradle.kts'))
    for module in sorted(actual - configured):
        findings.append(Finding('ERROR', 'unregistered-module', 'settings.gradle.kts', f'{module} 未登记到 java-modules.yaml'))
    for module in sorted(configured - actual):
        # 目标模块允许先登记后 include；只有存在目录/build 时才要求 include。
        mdir = module_dir(module)
        if (mdir / 'build.gradle.kts').exists():
            findings.append(Finding('ERROR', 'missing-include', rel(mdir / 'build.gradle.kts'), f'{module} 有 build.gradle.kts 但未 include'))
    return findings


# 检查 project 依赖方向。
def check_project_deps(config: dict[str, Any], fail_transition: bool) -> list[Finding]:
    """参数：
        config: 模块边界配置。
        fail_transition: 是否将过渡依赖视为错误。

    返回：
        检查结果列表。
    """
    findings: list[Finding] = []
    for module, meta in config['modules'].items():
        build_file = module_dir(module) / 'build.gradle.kts'
        if not build_file.exists():
            continue
        allowed = set(meta.get('allowedProjectDeps', []))
        transition = set(meta.get('transitionProjectDeps', []))
        for dep in parse_project_deps(build_file):
            if dep in allowed:
                continue
            if dep in transition:
                level = 'ERROR' if fail_transition else 'INFO'
                findings.append(Finding(level, 'transition-dependency', rel(build_file), f'{module} 仍依赖过渡模块 {dep}'))
                continue
            findings.append(Finding('ERROR', 'forbidden-dependency', rel(build_file), f'{module} 不允许依赖 {dep}'))
    return findings


# 检查 Java package 与 module root 是否匹配。
def check_packages(config: dict[str, Any]) -> list[Finding]:
    """参数：
        config: 模块边界配置。

    返回：
        检查结果列表。
    """
    findings: list[Finding] = []
    for module, meta in config['modules'].items():
        roots = list(meta.get('packageRoots', []))
        source_root = meta.get('sourceRoot')
        if not source_root or not roots:
            continue
        root_path = REPO_ROOT / source_root
        for java_file in java_files(root_path):
            pkg = package_name(java_file)
            if pkg is None:
                findings.append(Finding('ERROR', 'missing-package', rel(java_file), 'Java 文件缺少 package 声明'))
            elif not package_matches(pkg, roots):
                findings.append(Finding('ERROR', 'package-root', rel(java_file), f'package {pkg} 不属于 {module} 的 roots {roots}'))
    return findings


# 检查 forbidden imports。
def check_forbidden_imports(config: dict[str, Any]) -> list[Finding]:
    """参数：
        config: 模块边界配置。

    返回：
        检查结果列表。
    """
    findings: list[Finding] = []
    rules = list(config.get('forbiddenImports', []))
    for module, meta in config['modules'].items():
        source_root = meta.get('sourceRoot')
        if not source_root:
            continue
        for java_file in java_files(REPO_ROOT / source_root):
            pkg = package_name(java_file) or ''
            imps = imports(java_file)
            for rule in rules:
                src = rule['sourcePackage']
                if not (pkg == src or pkg.startswith(src + '.')):
                    continue
                for imp in imps:
                    for forbidden in rule.get('forbidden', []):
                        if imp == forbidden or imp.startswith(forbidden + '.'):
                            findings.append(Finding('ERROR', 'forbidden-import', rel(java_file), f'{pkg} 不得 import {imp}'))
    return findings


# 查找指定类名对应的源码文件。
def find_class_files(class_name: str) -> list[tuple[str, Path, str | None]]:
    """参数：
        class_name: Java 简单类名。

    返回：
        模块、文件路径与 package 名称元组列表。
    """
    result: list[tuple[str, Path, str | None]] = []
    for module_dir_path in (REPO_ROOT / 'java').iterdir():
        if not module_dir_path.is_dir():
            continue
        source_root = module_dir_path / 'src' / 'main' / 'java'
        if not source_root.exists():
            continue
        for java_file in source_root.rglob(f'{class_name}.java'):
            module = ':java:' + module_dir_path.name
            result.append((module, java_file, package_name(java_file)))
    return result


# 检查配置化 class placement 规则。
def check_class_placement(config: dict[str, Any]) -> list[Finding]:
    """参数：
        config: 模块边界配置。

    返回：
        检查结果列表。
    """
    findings: list[Finding] = []
    for rule in config.get('classPlacement', []):
        class_name = rule['className']
        required_module = rule['requiredModule']
        required_package = rule['requiredPackage']
        matches = find_class_files(class_name)
        if not matches:
            findings.append(Finding('ERROR', 'class-missing', class_name, f'{class_name} 未找到，期望位于 {required_module}/{required_package}'))
            continue
        for module, path, pkg in matches:
            if module != required_module or pkg != required_package:
                findings.append(Finding('ERROR', 'class-placement', rel(path), f'{class_name} 应位于 {required_module} 的 package {required_package}，当前 {module}/{pkg}'))
    return findings


# 解析命令行并执行模块边界检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='检查 Java module/package/dependency 边界')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG))
    parser.add_argument('--report', action='store_true', help='只报告，不因 ERROR 返回非零')
    parser.add_argument('--fail-transition', action='store_true', help='将 transition dependency 也视为失败')
    add_changed_files_arg(parser)
    args = parser.parse_args()

    # 自感知跳过：变更文件不匹配触发模式时直接 SKIP。
    changed_files = parse_changed_files(getattr(args, 'changed_files', None))
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    config = load_config(Path(args.config))
    findings: list[Finding] = []
    findings.extend(check_includes(config))
    findings.extend(check_project_deps(config, args.fail_transition))
    findings.extend(check_packages(config))
    findings.extend(check_forbidden_imports(config))
    findings.extend(check_class_placement(config))

    errors = [f for f in findings if f.level == 'ERROR']
    warnings = [f for f in findings if f.level == 'WARN']
    infos = [f for f in findings if f.level == 'INFO']
    if findings:
        print('=== java module boundary findings ===')
        for finding in findings:
            print(finding.format())
    print(
        'java module boundary summary: '
        f'errors={len(errors)} warnings={len(warnings)} infos={len(infos)}'
    )
    if errors and not args.report:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
