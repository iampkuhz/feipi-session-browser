"""用真实 PMD 和故障 CLI 验证原 Gradle Action，不复制 CPD 实现。"""

import json
import os
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = 'java/sample/src/main/java'

# 只替换外部工具，验证不易由合法源码稳定触发的退出码及 classloader 复用。
FAULT_CLI = r'''
package net.sourceforge.pmd.cli;
public final class PmdCli {
    private static int invocations;
    static int mainWithoutExit(String[] args) throws Exception {
        int count = ++invocations;
        System.setProperty("picocli.disable.closures", "changed-by-cli");
        java.util.logging.Logger root = java.util.logging.Logger.getLogger("");
        for (java.util.logging.Handler handler : root.getHandlers()) root.removeHandler(handler);
        root.addHandler(new java.util.logging.ConsoleHandler());
        Thread.currentThread().setContextClassLoader(new ClassLoader() {});
        java.nio.file.Files.writeString(
            java.nio.file.Path.of(System.getProperty("feipi.cpd.test.trace")), count + "\n",
            java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);
        String behavior = System.getProperty("feipi.cpd.test.behavior");
        if (behavior.equals("throw")) throw new IllegalStateException("synthetic CLI failure");
        if (behavior.equals("linkage")) throw new NoClassDefFoundError("synthetic missing class");
        String[] codes = behavior.split(",");
        return Integer.parseInt(codes[Math.min(count - 1, codes.length - 1)]);
    }
}
'''

RUNTIME_HARNESS = r'''
private class RuntimeChecksAction(
    private val fixturePath: String,
    private val classpath: List<String>,
) : org.gradle.api.Action<Task> {
    override fun execute(task: Task) {
        val fixture = java.io.File(fixturePath)
        val classes = fixture.resolve("fault-classes").apply { mkdirs() }
        val compiler = javax.tools.ToolProvider.getSystemJavaCompiler()
        check(compiler != null) { "JDK compiler required for CPD failure regression" }
        check(compiler.run(null, null, null, "-d", classes.absolutePath,
            fixture.resolve("PmdCli.java").absolutePath) == 0)
        val cases = groovy.json.JsonSlurper().parse(fixture.resolve("cases.json")) as List<*>
        cases.forEach { raw ->
            val case = raw as Map<*, *>
            val id = case["id"] as String
            val expected = case["status"] as String
            val root = fixture.resolve(id)
            val selectedClasspath = when (case["runtime"]) {
                "fault" -> listOf(classes.absolutePath)
                "missing" -> listOf(fixture.resolve("missing.jar").absolutePath)
                else -> classpath
            }
            val thread = Thread.currentThread()
            val originalLoader = thread.contextClassLoader
            val sentinelLoader = object : ClassLoader(originalLoader) {}
            val property = "picocli.disable.closures"
            val originalProperty = System.getProperty(property)
            val expectedProperty = if (case["seedProperty"] == true) "before-$id" else null
            val traceProperty = "feipi.cpd.test.trace"
            val behaviorProperty = "feipi.cpd.test.behavior"
            val originalTrace = System.getProperty(traceProperty)
            val originalBehavior = System.getProperty(behaviorProperty)
            val rootLogger = java.util.logging.Logger.getLogger("")
            val originalHandlers = rootLogger.handlers
            val sentinelHandler = object : java.util.logging.Handler() {
                override fun publish(record: java.util.logging.LogRecord) {}
                override fun flush() {}
                override fun close() {}
            }
            rootLogger.addHandler(sentinelHandler)
            val expectedHandlers = rootLogger.handlers
            thread.contextClassLoader = sentinelLoader
            if (expectedProperty == null) System.clearProperty(property)
            else System.setProperty(property, expectedProperty)
            val trace = root.resolve("trace.txt")
            trace.delete()
            System.setProperty(traceProperty, trace.absolutePath)
            System.setProperty(behaviorProperty, case["behavior"] as? String ?: "0")
            try {
                var failure: org.gradle.api.GradleException? = null
                try {
                    ReuseStandardCpdAction(
                        root.absolutePath, root.resolve("policy.json").absolutePath,
                        root.resolve("reports").absolutePath, root.resolve("work").absolutePath,
                        case["mode"] as? String ?: "full", case["changedFiles"] as? String,
                        listOf(root.resolve("java/sample/src/main/java").absolutePath), selectedClasspath,
                    ).execute(task)
                } catch (exc: org.gradle.api.GradleException) {
                    failure = exc
                }
                check(thread.contextClassLoader === sentinelLoader) { "$id leaked TCCL" }
                check(System.getProperty(property) == expectedProperty) { "$id leaked picocli property" }
                check(rootLogger.handlers.toList() == expectedHandlers.toList()) { "$id leaked JUL handlers" }
                check((failure == null) == (expected == "PASS")) { "$id unexpected failure: $failure" }
                val summary = groovy.json.JsonSlurper().parse(
                    root.resolve("reports/standard-cpd-summary.json")) as Map<*, *>
                check(summary["status"] == expected) { "$id wrong status: $summary" }
                if (expected == "FAIL") {
                    check(failure!!.message!!.contains("tool-execution-error")) { "$id wrong reason: $failure" }
                }
                task.logger.lifecycle("CPD_RUNTIME_CASE id=$id status=$expected context=restored")
            } finally {
                thread.contextClassLoader = originalLoader
                mapOf(property to originalProperty, traceProperty to originalTrace,
                    behaviorProperty to originalBehavior).forEach { (key, value) ->
                    if (value == null) System.clearProperty(key) else System.setProperty(key, value)
                }
                rootLogger.handlers.forEach { rootLogger.removeHandler(it) }
                originalHandlers.forEach { rootLogger.addHandler(it) }
                sentinelHandler.close()
            }
        }
    }
}

val pmdRuntime = configurations.create("pmdRuntime")
repositories {
    maven("https://maven.aliyun.com/repository/central")
    mavenCentral()
}
dependencies {
    add("pmdRuntime", "net.sourceforge.pmd:pmd-cli:PMD_VERSION")
    add("pmdRuntime", "net.sourceforge.pmd:pmd-java:PMD_VERSION")
}
val runtimeFiles = pmdRuntime.resolve().map { it.absolutePath }.sorted()
tasks.register("runtimeChecks") {
    doLast(RuntimeChecksAction(rootDir.absolutePath, runtimeFiles))
}
'''


def _method(name: str, prefix: str) -> str:
    statements = '\n'.join(f'int {prefix}{i} = value + {i};' for i in range(48))
    return f'int {name}(int value) {{\n{statements}\nreturn {prefix}47;\n}}'


def _profiles() -> list[dict]:
    return json.loads((REPO_ROOT / 'java/gradle/config/reuse-policy/policy.json').read_text())[
        'standardDuplicateDetection'
    ]['profiles']


def _write_case(
    fixture: Path,
    case_id: str,
    sources: dict[str, str],
    status: str,
    profiles: list[dict],
    **options: object,
) -> dict:
    root = fixture / case_id
    source_dir = root / SOURCE_DIR
    source_dir.mkdir(parents=True)
    for name, source in sources.items():
        (source_dir / name).write_text(source, encoding='utf-8')
    (root / 'policy.json').write_text(
        json.dumps({'standardDuplicateDetection': {'profiles': profiles}}), encoding='utf-8'
    )
    return {'id': case_id, 'status': status, 'inputCount': len(sources), **options}


def _prepare_fixture(fixture: Path) -> list[dict]:
    profiles = _profiles()
    first = f'class First {{ {_method("calculate", "first")} }}'
    similar = f'class Second {{ {_method("transform", "second")} }}'
    exact = f'class Second {{ {_method("calculate", "first")} }}'
    sibling = (
        f'class Siblings {{ {_method("calculate", "first")} {_method("transform", "second")} }}'
    )
    broken = 'class Broken { String broken = "unterminated\n }'
    clean_sources = {'First.java': first, 'Second.java': similar}
    cases = [
        _write_case(fixture, 'clean', {'First.java': first}, 'PASS', profiles),
        _write_case(
            fixture, 'normalized-siblings', {'Siblings.java': sibling}, 'BLOCKED', profiles
        ),
        _write_case(
            fixture, 'cross-file-similar', clean_sources, 'PASS', profiles, seedProperty=True
        ),
        _write_case(
            fixture,
            'cross-file-exact',
            {'First.java': first, 'Second.java': exact},
            'BLOCKED',
            profiles,
        ),
        _write_case(fixture, 'lexical-error', {'Broken.java': broken}, 'FAIL', profiles),
        _write_case(
            fixture,
            'mixed-error-duplicates',
            {'Siblings.java': sibling, 'Broken.java': broken},
            'FAIL',
            profiles,
        ),
        _write_case(fixture, 'empty', {}, 'PASS', profiles, runtime='missing'),
        _write_case(
            fixture,
            'missing-jar',
            {'First.java': first},
            'FAIL',
            profiles,
            runtime='missing',
            seedProperty=True,
        ),
    ]
    for behavior, status in [
        ('0', 'PASS'),
        ('4', 'BLOCKED'),
        ('1', 'FAIL'),
        ('2', 'FAIL'),
        ('5', 'FAIL'),
        ('4,5,0', 'FAIL'),
        ('throw', 'FAIL'),
        ('linkage', 'FAIL'),
    ]:
        cases.append(
            _write_case(
                fixture,
                f'fault-{behavior.replace(",", "-")}',
                clean_sources,
                status,
                profiles,
                runtime='fault',
                behavior=behavior,
                seedProperty=True,
            )
        )
    # 输入选择也由同一个真实 Action 执行，不以字符串断言替代。
    cases.append(
        _write_case(
            fixture,
            'incremental-selection',
            clean_sources,
            'PASS',
            profiles,
            mode='incremental',
            changedFiles=json.dumps([f'{SOURCE_DIR}/First.java']),
            inputCount=1,
        )
    )
    cases.append(
        _write_case(
            fixture,
            'incremental-expanded',
            clean_sources,
            'PASS',
            profiles,
            mode='incremental',
            changedFiles='["java/build.gradle.kts"]',
        )
    )
    (fixture / 'cases.json').write_text(json.dumps(cases), encoding='utf-8')
    (fixture / 'PmdCli.java').write_text(FAULT_CLI, encoding='utf-8')
    (fixture / 'settings.gradle.kts').write_text('rootProject.name = "cpd-runtime-regression"\n')
    text = (REPO_ROOT / 'java/build.gradle.kts').read_text(encoding='utf-8')
    start = text.index('private class ReuseStandardCpdAction(')
    end = text.index('\ngradle.projectsEvaluated {', start)
    with (REPO_ROOT / 'java/gradle/libs.versions.toml').open('rb') as stream:
        pmd_version = tomllib.load(stream)['versions']['pmd']
    (fixture / 'build.gradle.kts').write_text(
        text[start:end] + RUNTIME_HARNESS.replace('PMD_VERSION', pmd_version), encoding='utf-8'
    )
    return cases


def _assert_reports(fixture: Path, cases: list[dict]) -> None:
    for case in cases:
        root = fixture / case['id']
        summary = json.loads((root / 'reports/standard-cpd-summary.json').read_text())
        assert summary['status'] == case['status'], case['id']
        assert summary['cpdInputCount'] == case['inputCount'], case['id']
        assert summary['profiles'] == [profile['id'] for profile in _profiles()]
        listed_inputs = (root / 'work/reuse-cpd-file-list.txt').read_text().splitlines()
        assert len(listed_inputs) == case['inputCount']
        assert summary['cpdInputFiles'] == [
            Path(path).relative_to(root).as_posix() for path in listed_inputs
        ]
        if 'runtime' not in case:
            assert (root / 'reports/cpd-exact-blocks.xml').is_file()
            normalized_reports = list((root / 'reports').glob('cpd-normalized-*/*.xml'))
            single_file_lists = list((root / 'work').glob('cpd-normalized-*/*.file-list.txt'))
            assert len(normalized_reports) == len(single_file_lists) == case['inputCount']
            assert sorted(path.read_text().strip() for path in single_file_lists) == sorted(
                listed_inputs
            )
        if case.get('runtime') == 'fault':
            expected = [1] if case['behavior'] in ('throw', 'linkage') else [1, 2, 3]
            assert [int(line) for line in (root / 'trace.txt').read_text().splitlines()] == expected
    assert not list((fixture / 'empty/reports').glob('*.xml'))
    siblings = fixture / 'normalized-siblings/reports'
    assert '<duplication ' not in (siblings / 'cpd-exact-blocks.xml').read_text()
    assert any(
        '<duplication ' in path.read_text() for path in siblings.glob('cpd-normalized-*/*.xml')
    )
    cross = fixture / 'cross-file-exact/reports'
    assert '<duplication ' in (cross / 'cpd-exact-blocks.xml').read_text()
    assert all(
        '<duplication ' not in path.read_text() for path in cross.glob('cpd-normalized-*/*.xml')
    )
    for case_id in ('lexical-error', 'mixed-error-duplicates'):
        summary = json.loads((fixture / case_id / 'reports/standard-cpd-summary.json').read_text())
        assert any('exit=5' in failure for failure in summary['failures'])


def test_original_cpd_action_with_real_pmd_and_configuration_cache(tmp_path: Path) -> None:
    cases = _prepare_fixture(tmp_path)
    command = [
        str(REPO_ROOT / 'java' / ('gradlew.bat' if os.name == 'nt' else 'gradlew')),
        '-p',
        str(tmp_path),
        '--console=plain',
        '--configuration-cache',
        '--rerun-tasks',
        'runtimeChecks',
    ]
    for run in range(2):
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        (tmp_path / f'gradle-{run}.log').write_text(result.stdout, encoding='utf-8')
        assert result.returncode == 0, result.stdout[-12000:]
        assert result.stdout.count('CPD_RUNTIME_CASE ') == len(cases)
        assert (
            'Configuration cache entry stored.' in result.stdout
            if run == 0
            else ('Configuration cache entry reused.' in result.stdout)
        )
        _assert_reports(tmp_path, cases)
