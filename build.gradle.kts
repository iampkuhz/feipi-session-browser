plugins {
    base
    jacoco
}

layout.buildDirectory.set(layout.projectDirectory.dir(".local/gradle/root-build"))

group = "com.feipi.session.browser"
version = file("VERSION").readText().trim()

subprojects {
    group = rootProject.group
    version = rootProject.version
}

repositories {
    maven("https://maven.aliyun.com/repository/central")
    mavenCentral()
}

dependencyLocking {
    lockAllConfigurations()
}

// 只有叶子子项目才有 check 任务。
val leafSubprojects by lazy { subprojects.filter { it.childProjects.isEmpty() } }

// 根项目 check 聚合所有子项目的 check 任务。
tasks.named("check") {
    dependsOn(leafSubprojects.map { "${it.path}:check" })
}

// ============================================================
// qualityFull —— 慢速质量门，聚合 check + 报告 + fixture。
// ============================================================
val qualityFull = tasks.register("qualityFull") {
    group = "verification"
    description = "Full quality gate: check + root JaCoCo report + functional fixtures."
    dependsOn("check")
}

// ============================================================
// jacocoRootReport —— 跨模块聚合 JaCoCo 覆盖率报告（真实聚合）。
// ============================================================
val jacocoRootReport = tasks.register("jacocoRootReport", JacocoReport::class.java) {
    group = "verification"
    description = "Aggregated JaCoCo report across all modules."
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

// 聚合各子项目的 JaCoCo execution data、源码和 class 目录。
gradle.projectsEvaluated {
    jacocoRootReport.configure {
        val participating = leafSubprojects.filter { sub ->
            sub.tasks.names.contains("jacocoTestReport")
        }
        dependsOn(participating.map { "${it.path}:jacocoTestReport" })

        executionData.from(participating.map { sub ->
            sub.tasks.named("jacocoTestReport", JacocoReport::class.java).map { it.executionData }
        })
        sourceDirectories.from(participating.map { sub ->
            sub.tasks.named("jacocoTestReport", JacocoReport::class.java).map { it.sourceDirectories }
        })
        classDirectories.from(participating.map { sub ->
            sub.tasks.named("jacocoTestReport", JacocoReport::class.java).map { it.classDirectories }
        })
    }
    qualityFull.configure {
        dependsOn(jacocoRootReport)
    }
}

// ============================================================
// javadocVerify —— 聚合 Javadoc 验证。
// ============================================================
val javadocVerify = tasks.register("javadocVerify") {
    group = "verification"
    description = "Verifies Javadoc for all modules with production source code."
}

gradle.projectsEvaluated {
    javadocVerify.configure {
        dependsOn(leafSubprojects.filter { sub ->
            sub.file("src/main/java").exists()
        }.map { "${it.path}:javadoc" })
    }
}

tasks.named("check") {
    dependsOn(javadocVerify)
}

// ============================================================
// verifyNoSkippedJavaTests —— 零跳过/零中止强制检查。
// 配置缓存兼容：动作逻辑提取到顶层函数，避免捕获脚本对象。
// ============================================================
val verifyNoSkippedJavaTests = tasks.register("verifyNoSkippedJavaTests") {
    group = "verification"
    description = "Fails if any Java test has been skipped or aborted."
}

gradle.projectsEvaluated {
    verifyNoSkippedJavaTests.configure {
        dependsOn(leafSubprojects.mapNotNull { sub ->
            sub.tasks.names.takeIf { "test" in it }?.let { "${sub.path}:test" }
        })

        // 配置时解析所有测试结果和源码目录路径为字符串列表，避免执行时引用脚本对象。
        val testEntries: List<String> = leafSubprojects.map { sub ->
            listOf(
                sub.path,
                sub.layout.buildDirectory.dir("test-results/test").get().asFile.absolutePath,
                sub.file("src/test/java").absolutePath,
                sub.file("src/test/kotlin").absolutePath,
            ).joinToString("\u0000")
        }
        val testDirs: List<String> = testEntries.map { entry ->
            entry.split("\u0000", limit = 4)[1]
        }
        val testSourceDirs: List<String> = testEntries.flatMap { entry ->
            entry.split("\u0000", limit = 4).drop(2)
        }
        // 声明测试目录为 inputs，确保 up-to-date 检查正确。
        inputs.files(testDirs).withPropertyName("testResultDirs")
            .optional(true)
        inputs.files(testSourceDirs).withPropertyName("testSourceDirs")
            .optional(true)
        outputs.file(layout.buildDirectory.file("reports/verify-no-skipped-tests/result.txt"))
            .withPropertyName("resultFile")
        doLast(checkNoSkippedTestsAction(testEntries, layout.buildDirectory.file("reports/verify-no-skipped-tests/result.txt").get().asFile.absolutePath))
    }
}

tasks.named("check") {
    dependsOn(verifyNoSkippedJavaTests)
}

// ============================================================
// verifyLeanQualityStack —— 确保被排除的质量工具不存在。
// 配置缓存兼容：动作逻辑提取到顶层函数。
// ============================================================
val verifyLeanQualityStack = tasks.register("verifyLeanQualityStack") {
    group = "verification"
    description = "Verifies that excluded quality tools are not present in the build."

    // 声明真实 inputs/outputs，确保配置缓存兼容和 up-to-date 检查。
    val catalogPath = file("gradle/libs.versions.toml").absolutePath
    val resultFilePath = layout.buildDirectory.file("reports/verify-lean-quality/result.txt").get().asFile.absolutePath
    inputs.file(catalogPath).withPropertyName("versionCatalog")
    outputs.file(resultFilePath).withPropertyName("resultFile")
    doLast(checkLeanQualityStackAction(catalogPath, resultFilePath))
}

tasks.named("check") {
    dependsOn(verifyLeanQualityStack)
}

// Java source 专属规则由 quality-gates registry 在一个 JavaExec 中聚合。
// 默认 registry 一次执行注释语言、record Javadoc 与 PMD 抑制规则。
tasks.named("check") {
    dependsOn(":java:tests:quality-gates:runJavaQualityGates")
}

// ============================================================
// 顶层动作函数 —— 配置缓存兼容。
// 这些函数编译为静态方法，不持有构建脚本引用。
// doLast 通过返回 Action<Task> 的 lambda 只捕获局部变量。
// ============================================================

/**
 * verifyLeanQualityStack 的执行动作。
 * 检查版本目录不包含被排除的质量工具条目。
 * resultFilePath 用于声明 outputs，使 task 可被 up-to-date 检查。
 */
private fun checkLeanQualityStackAction(catalogPath: String, resultFilePath: String = ""): org.gradle.api.Action<Task> {
    return org.gradle.api.Action<Task> {
        val catalogFile = java.io.File(catalogPath)
        if (catalogFile.exists()) {
            val catalogContent = catalogFile.readText()
            val forbiddenEntries = listOf(
                "spotbugs-plugin", "forbiddenapis", "pitest", "cyclonedx",
                "errorprone", "nullaway", "spotbugs-annotations",
            )
            forbiddenEntries.forEach { entry ->
                if (catalogContent.contains(Regex("""\b${Regex.escape(entry)}\b"""))) {
                    throw org.gradle.api.GradleException("Version catalog contains excluded tool entry: $entry")
                }
            }
        }
        logger.lifecycle("verifyLeanQualityStack: PASSED – no excluded tools detected in catalog.")
        if (resultFilePath.isNotEmpty()) {
            val resultFile = java.io.File(resultFilePath)
            resultFile.parentFile.mkdirs()
            resultFile.writeText("PASSED\n", Charsets.UTF_8)
        }
    }
}

/**
 * verifyNoSkippedJavaTests 的执行动作。
 * 扫描所有测试目录的 XML 结果，确保无跳过/中止测试。
 * resultFilePath 用于声明 outputs，使 task 可被 up-to-date 检查。
 */
private fun checkNoSkippedTestsAction(
    testEntries: List<String>,
    resultFilePath: String = "",
): org.gradle.api.Action<Task> {
    return org.gradle.api.Action<Task> {
        var totalSkipped = 0
        var totalErrors = 0
        var totalFailures = 0
        var totalAborted = 0
        var totalTests = 0
        var filesFound = 0
        val missingReports = mutableListOf<String>()

        testEntries.forEach { entry ->
            val parts = entry.split("\u0000")
            val projectPath = parts.getOrElse(0) { "<unknown>" }
            val dirPath = parts.getOrElse(1) { "" }
            val sourceDirs = parts.drop(2).map { java.io.File(it) }
            val hasTestSources = sourceDirs.any { sourceDir ->
                sourceDir.exists() && sourceDir.walkTopDown().any { sourceFile ->
                    sourceFile.isFile && (sourceFile.extension == "java" || sourceFile.extension == "kt")
                }
            }
            val testResultsDir = java.io.File(dirPath)
            var moduleFilesFound = 0
            if (testResultsDir.exists()) {
                testResultsDir.walkTopDown()
                    .filter { it.name.startsWith("TEST-") && it.extension == "xml" }
                    .forEach { file ->
                        filesFound++
                        moduleFilesFound++
                        val content = file.readText()
                        val skippedMatch = Regex("""skipped="(\d+)"""").find(content)
                        val errorsMatch = Regex("""errors="(\d+)"""").find(content)
                        val failuresMatch = Regex("""failures="(\d+)"""").find(content)
                        val testsMatch = Regex("""tests="(\d+)"""").find(content)
                        totalSkipped += skippedMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        totalErrors += errorsMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        totalFailures += failuresMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        totalTests += testsMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        if (Regex("""(?i)(aborted|TestAborted)""").containsMatchIn(content)) {
                            totalAborted++
                        }
                    }
            }
            if (hasTestSources && moduleFilesFound == 0) {
                missingReports.add("$projectPath ($dirPath)")
            }
        }

        if (missingReports.isNotEmpty()) {
            throw org.gradle.api.GradleException(
                "Missing Java test result XML for module(s) with test sources: " +
                    missingReports.joinToString(", ")
            )
        }

        if (totalTests == 0 && filesFound > 0) {
            throw org.gradle.api.GradleException(
                "Found 0 Java tests in $filesFound test result XML file(s)."
            )
        }
        if (totalFailures > 0) {
            throw org.gradle.api.GradleException(
                "Found $totalFailures failed Java test(s). Failing tests are not allowed."
            )
        }
        if (totalSkipped > 0) {
            throw org.gradle.api.GradleException(
                "Found $totalSkipped skipped test(s). Skipped tests are not allowed."
            )
        }
        if (totalErrors > 0) {
            throw org.gradle.api.GradleException(
                "Found $totalErrors errored Java test(s). Errors are not allowed."
            )
        }
        if (totalAborted > 0) {
            throw org.gradle.api.GradleException(
                "Found $totalAborted aborted Java test result XML file(s). Aborted tests are not allowed."
            )
        }
        if (filesFound == 0) {
            logger.lifecycle(
                "verifyNoSkippedJavaTests: No test result XMLs found. " +
                    "This may be expected if no modules have test sources."
            )
        } else {
            logger.lifecycle(
                "verifyNoSkippedJavaTests: $totalTests test(s) in $filesFound file(s), " +
                    "0 failed, 0 errored, 0 skipped, 0 aborted."
            )
        }
        if (resultFilePath.isNotEmpty()) {
            val resultFile = java.io.File(resultFilePath)
            resultFile.parentFile.mkdirs()
            resultFile.writeText(
                "$totalTests tests in $filesFound files, 0 failed, 0 errored, 0 skipped, 0 aborted.\n",
                Charsets.UTF_8,
            )
        }
    }
}

// ============================================================
// Reuse quality gates —— PMD only.
// Copy-paste duplicate 检测直接调用 PMD CPD CLI；语义类复用规则交给 pmdMain。
// ============================================================

val pmdCpdRuntime = configurations.create("pmdCpdRuntime") {
    isCanBeConsumed = false
    isCanBeResolved = true
}

dependencies {
    add("pmdCpdRuntime", libs.pmd.cli)
    add("pmdCpdRuntime", libs.pmd.java)
}

val reuseAnalysisReportDir = layout.buildDirectory.dir("reports/reuse-analysis")
val policyFilePath = file("config/reuse-policy/policy.json").absolutePath

private class ReuseStandardCpdAction(
    private val rootPath: String,
    private val policyPath: String,
    private val reportDirPath: String,
    private val workDirPath: String,
    private val mode: String,
    private val changedFilesJson: String?,
    private val sourceDirPaths: List<String>,
    private val pmdClasspathEntries: List<String>,
) : org.gradle.api.Action<Task> {
    private data class Profile(
        val id: String,
        val minimumTokens: Int,
        val ignoreAnnotations: Boolean,
        val ignoreLiterals: Boolean,
        val ignoreIdentifiers: Boolean,
        val skipDuplicateFiles: Boolean,
        val scope: String,
    )

    private class CpdExecutionFailure(
        val reasonCode: String,
        message: String,
    ) : RuntimeException(message)

    override fun execute(task: Task) {
        val root = java.io.File(rootPath)
        val policyFile = java.io.File(policyPath)
        val reportDir = java.io.File(reportDirPath)
        val workDir = java.io.File(workDirPath)
        val sourceDirs = sourceDirPaths.map { java.io.File(it) }.filter { it.isDirectory }
        reportDir.mkdirs()
        workDir.mkdirs()
        var profiles = emptyList<Profile>()
        val failures = mutableListOf<String>()
        val javaExecutable = java.io.File(System.getProperty("java.home"), "bin/java").absolutePath
        val pmdClasspath = pmdClasspathEntries.joinToString(java.io.File.pathSeparator)
        val allSourceFiles = sourceDirs.flatMap { dir ->
            dir.walkTopDown().filter { it.isFile && it.extension == "java" }.toList()
        }.distinctBy { it.toPath().toAbsolutePath().normalize().toString() }
            .sortedBy { relativePath(root, it) }
        val summaryFile = reportDir.resolve("standard-cpd-summary.json")
        var changedFiles = emptyList<String>()
        var changedFilesSource = if (mode == "full") "full-scan" else "QUALITY_CHANGED_FILES"

        try {
            if (mode != "incremental" && mode != "full") {
                throw CpdExecutionFailure(
                    "input-unavailable",
                    "Invalid feipiReuseCpdMode=$mode",
                )
            }

            val cpdInputFiles = if (mode == "full") {
                allSourceFiles
            } else {
                changedFiles = changedFilesJson?.let { parseChangedFiles(it, root) }
                    ?: throw CpdExecutionFailure(
                        "input-unavailable",
                        "QUALITY_CHANGED_FILES is required in incremental mode.",
                    )
                if (changedFiles.any { requiresCompleteCpdInput(it) }) {
                    // 仍是 incremental profile，只是该类改动无法安全缩小 CPD 输入范围。
                    changedFilesSource = "QUALITY_CHANGED_FILES(expanded-to-all-sources)"
                    allSourceFiles
                } else {
                    selectProductionJavaFiles(root, changedFiles)
                }
            }
            profiles = loadProfiles(policyFile)

            val sharedFileList = writeFileList(
                cpdInputFiles,
                workDir.resolve("reuse-cpd-file-list.txt"),
            )
            if (cpdInputFiles.isEmpty()) {
                writeReuseCpdSummary(
                    summaryFile,
                    root,
                    "PASS",
                    profiles,
                    changedFiles,
                    cpdInputFiles,
                    changedFilesSource,
                    reportDir,
                    failures,
                    if (mode == "full") {
                        "No production Java files; CPD was not invoked."
                    } else {
                        "No changed production Java files; CPD was not invoked."
                    },
                )
                task.logger.lifecycle("reuseStandardCpd: no CPD input files (mode=$mode)")
                return
            }

            fun runCpd(profile: Profile, fileList: java.io.File, reportFile: java.io.File): Int {
                reportFile.parentFile.mkdirs()
                val command = listOf(
                    javaExecutable,
                    "-cp",
                    pmdClasspath,
                    "net.sourceforge.pmd.cli.PmdCli",
                ) + reuseCpdArgs(profile, fileList, reportFile, root)
                return ProcessBuilder(command).directory(root).inheritIO().start().waitFor()
            }

            profiles.forEach { profile ->
                if (profile.scope == "same-file") {
                    cpdInputFiles.forEach { sourceFile ->
                        val relative = relativePath(root, sourceFile)
                        val reportName = sanitizeProfileId(relative) + ".xml"
                        val reportFile = reportDir.resolve("cpd-${profile.id}").resolve(reportName)
                        val singleFileList = writeFileList(
                            listOf(sourceFile),
                            workDir.resolve("cpd-${profile.id}")
                                .resolve(sanitizeProfileId(relative) + ".file-list.txt"),
                        )
                        val exitValue = runCpd(profile, singleFileList, reportFile)
                        if (exitValue != 0) {
                            failures.add(
                                "${profile.id}:${relative}(exit=$exitValue, report=${reportFile.absolutePath})"
                            )
                        }
                    }
                } else {
                    val reportFile = reportDir.resolve("cpd-${profile.id}.xml")
                    val exitValue = runCpd(profile, sharedFileList, reportFile)
                    if (exitValue != 0) {
                        failures.add("${profile.id}(exit=$exitValue, report=${reportFile.absolutePath})")
                    }
                }
            }
            writeReuseCpdSummary(
                summaryFile,
                root,
                if (failures.isEmpty()) "PASS" else "BLOCKED",
                profiles,
                changedFiles,
                cpdInputFiles,
                changedFilesSource,
                reportDir,
                failures,
                if (failures.isEmpty()) "" else "PMD CPD duplicate violations.",
            )
            if (failures.isNotEmpty()) {
                task.logger.lifecycle(
                    "GATE_TASK_RESULT task=${task.path} status=BLOCKED"
                )
                throw org.gradle.api.GradleException(
                    "PMD CPD duplicate violations: ${failures.joinToString(", ")}"
                )
            }
            task.logger.lifecycle(
                "reuseStandardCpd: PMD CPD PASS " +
                    "(${profiles.size} profile(s), mode=$mode, input=${cpdInputFiles.size})"
            )
        } catch (exc: CpdExecutionFailure) {
            writeReuseCpdSummary(
                summaryFile,
                root,
                "FAIL",
                profiles,
                changedFiles,
                emptyList(),
                changedFilesSource,
                reportDir,
                failures,
                exc.message ?: exc.reasonCode,
            )
            // executor 只需要理解这条通用 task/status/reason 协议，不需要认识 CPD。
            task.logger.lifecycle(
                "GATE_TASK_RESULT task=${task.path} status=FAIL reason=${exc.reasonCode}"
            )
            throw org.gradle.api.GradleException(
                "reuseStandardCpd failed (${exc.reasonCode}): ${exc.message}",
                exc,
            )
        }
    }

    private fun parseChangedFiles(value: String, root: java.io.File): List<String> {
        val parsed = try {
            groovy.json.JsonSlurper().parseText(value)
        } catch (exc: RuntimeException) {
            throw CpdExecutionFailure(
                "input-unavailable",
                "QUALITY_CHANGED_FILES must be valid JSON.",
            )
        }
        val values = parsed as? List<*>
            ?: throw CpdExecutionFailure(
                "input-unavailable",
                "QUALITY_CHANGED_FILES must be a JSON string array.",
            )
        if (values.any { it !is String }) {
            throw CpdExecutionFailure(
                "input-unavailable",
                "QUALITY_CHANGED_FILES must contain only string paths.",
            )
        }
        return normalizeChangedPaths(values.filterIsInstance<String>(), root)
    }

    private fun normalizeChangedPaths(paths: List<String>, root: java.io.File): List<String> {
        val rootPath = root.toPath().toAbsolutePath().normalize()
        val seen = linkedSetOf<String>()
        paths.forEach { raw ->
            val value = raw.replace('\\', '/').trim().removePrefix("./")
            if (value.isBlank()) {
                return@forEach
            }
            val candidate = java.io.File(value)
            val normalized = (
                if (candidate.isAbsolute) candidate.toPath() else rootPath.resolve(value)
            ).toAbsolutePath().normalize()
            if (!normalized.startsWith(rootPath)) {
                return@forEach
            }
            val relative = rootPath.relativize(normalized).toString()
                .replace(java.io.File.separatorChar, '/')
            if (relative.isNotBlank()) {
                seen.add(relative)
            }
        }
        return seen.toList()
    }

    private fun selectProductionJavaFiles(
        root: java.io.File,
        changedFiles: List<String>,
    ): List<java.io.File> = changedFiles.mapNotNull { relative ->
        if (!isProductionJavaPath(relative)) {
            return@mapNotNull null
        }
        java.io.File(root, relative).takeIf { it.isFile }
    }.distinctBy { it.toPath().toAbsolutePath().normalize().toString() }

    private fun isProductionJavaPath(path: String): Boolean =
        path.startsWith("java/") && path.contains("/src/main/java/") && path.endsWith(".java")

    private fun requiresCompleteCpdInput(path: String): Boolean =
        path == "build.gradle.kts" ||
            path == "settings.gradle.kts" ||
            path == "config/reuse-policy" ||
            path.startsWith("config/reuse-policy/") ||
            (path.startsWith("java/") && path.endsWith("/build.gradle.kts"))

    private fun loadProfiles(policyFile: java.io.File): List<Profile> {
        val defaultProfile = Profile(
            id = "exact-blocks",
            minimumTokens = 50,
            ignoreAnnotations = true,
            ignoreLiterals = false,
            ignoreIdentifiers = false,
            skipDuplicateFiles = true,
            scope = "all-sources",
        )
        if (!policyFile.isFile) {
            return listOf(defaultProfile)
        }
        val policy = groovy.json.JsonSlurper().parse(policyFile) as? Map<*, *> ?: return listOf(defaultProfile)
        val standard = policy["standardDuplicateDetection"] as? Map<*, *> ?: return listOf(defaultProfile)
        val base = Profile(
            id = stringValue(standard["id"], defaultProfile.id),
            minimumTokens = intValue(standard["minimumTokens"], defaultProfile.minimumTokens),
            ignoreAnnotations = booleanValue(standard["ignoreAnnotations"], defaultProfile.ignoreAnnotations),
            ignoreLiterals = booleanValue(standard["ignoreLiterals"], defaultProfile.ignoreLiterals),
            ignoreIdentifiers = booleanValue(standard["ignoreIdentifiers"], defaultProfile.ignoreIdentifiers),
            skipDuplicateFiles = booleanValue(standard["skipDuplicateFiles"], defaultProfile.skipDuplicateFiles),
            scope = stringValue(standard["scope"], defaultProfile.scope),
        )
        val rawProfiles = standard["profiles"] as? List<*> ?: return listOf(base)
        return rawProfiles.mapIndexedNotNull { index, raw ->
            val profile = raw as? Map<*, *> ?: return@mapIndexedNotNull null
            Profile(
                id = sanitizeProfileId(stringValue(profile["id"], "profile-${index + 1}")),
                minimumTokens = intValue(profile["minimumTokens"], base.minimumTokens),
                ignoreAnnotations = booleanValue(profile["ignoreAnnotations"], base.ignoreAnnotations),
                ignoreLiterals = booleanValue(profile["ignoreLiterals"], base.ignoreLiterals),
                ignoreIdentifiers = booleanValue(profile["ignoreIdentifiers"], base.ignoreIdentifiers),
                skipDuplicateFiles = booleanValue(profile["skipDuplicateFiles"], base.skipDuplicateFiles),
                scope = stringValue(profile["scope"], base.scope),
            )
        }.ifEmpty { listOf(base) }
    }

    private fun writeFileList(files: List<java.io.File>, fileList: java.io.File): java.io.File {
        fileList.parentFile.mkdirs()
        fileList.writeText(
            files.joinToString("\n") { it.toPath().toAbsolutePath().normalize().toString() } +
                if (files.isEmpty()) "" else "\n",
            Charsets.UTF_8,
        )
        return fileList
    }

    private fun reuseCpdArgs(
        profile: Profile,
        fileList: java.io.File,
        reportFile: java.io.File,
        root: java.io.File,
    ): List<String> = buildList {
        add("cpd")
        add("--language")
        add("java")
        add("--minimum-tokens")
        add(profile.minimumTokens.toString())
        if (profile.skipDuplicateFiles) add("--skip-duplicate-files")
        if (profile.ignoreAnnotations) add("--ignore-annotations")
        if (profile.ignoreLiterals) add("--ignore-literals")
        if (profile.ignoreIdentifiers) add("--ignore-identifiers")
        add("--format")
        add("xml")
        add("--report-file")
        add(reportFile.absolutePath)
        add("--relativize-paths-with")
        add(root.absolutePath)
        add("--file-list")
        add(fileList.absolutePath)
    }

    private fun writeReuseCpdSummary(
        summaryFile: java.io.File,
        root: java.io.File,
        status: String,
        profiles: List<Profile>,
        changedFiles: List<String>,
        inputFiles: List<java.io.File>,
        changedFilesSource: String,
        reportDir: java.io.File,
        failures: List<String>,
        reason: String,
    ) {
        summaryFile.parentFile.mkdirs()
        val summary = linkedMapOf<String, Any?>(
            "engine" to "PMD_CPD_CLI",
            "status" to status,
            "mode" to mode,
            "inputMechanism" to "pmd-cpd --file-list",
            "changedFilesSource" to changedFilesSource,
            "changedFileCount" to changedFiles.size,
            "profiles" to profiles.map { it.id },
            "reports" to reportDir.absolutePath,
            "cpdInputFiles" to inputFiles.map { relativePath(root, it) },
            "cpdInputCount" to inputFiles.size,
            "fullScan" to (mode == "full"),
            "dirScanUsed" to false,
            "failures" to failures,
            "reason" to reason,
        )
        summaryFile.writeText(
            groovy.json.JsonOutput.prettyPrint(groovy.json.JsonOutput.toJson(summary)) + "\n",
            Charsets.UTF_8,
        )
    }

    private fun relativePath(root: java.io.File, file: java.io.File): String =
        root.toPath().toAbsolutePath().normalize()
            .relativize(file.toPath().toAbsolutePath().normalize())
            .toString().replace(java.io.File.separatorChar, '/')

    private fun sanitizeProfileId(value: String): String =
        value.replace(Regex("[^A-Za-z0-9._-]"), "-").ifBlank { "profile" }

    private fun booleanValue(value: Any?, defaultValue: Boolean): Boolean =
        if (value is Boolean) value else defaultValue

    private fun intValue(value: Any?, defaultValue: Int): Int =
        if (value is Number) value.toInt() else defaultValue

    private fun stringValue(value: Any?, defaultValue: String): String =
        if (value is String && value.isNotBlank()) value else defaultValue
}

gradle.projectsEvaluated {
    val productionModules = leafSubprojects.filter { sub ->
        sub.path != ":java:tests:support"
            && sub.path != ":java:tests:architecture"
            && sub.path != ":java:tests:contracts"
            && sub.file("src/main/java").isDirectory
    }
    val productionSourceDirs = productionModules.map { it.file("src/main/java") }

    tasks.register("reuseStandardCpd") {
        group = "verification"
        description = "使用 PMD CPD CLI 执行标准重复代码检测。"

        val policyFileRef = file(policyFilePath)
        val reportDir = reuseAnalysisReportDir.get().asFile
        val workDir = layout.buildDirectory.dir("tmp/reuse-standard-cpd").get().asFile
        val explicitMode = (findProperty("feipiReuseCpdMode") as? String)?.trim()
            ?.takeIf { it.isNotEmpty() }
        val qualityExecutionMode = providers.environmentVariable("QUALITY_EXECUTION_MODE").orNull
        val configuredMode = explicitMode ?: qualityExecutionMode ?: "incremental"
        val changedFilesJson = providers.environmentVariable("QUALITY_CHANGED_FILES").orNull
        val rootPath = rootDir.absolutePath
        val sourceDirPaths = productionSourceDirs.map { it.absolutePath }
        val pmdClasspathEntries = pmdCpdRuntime.resolve().map { it.absolutePath }.sorted()
        inputs.file(policyFileRef).withPropertyName("policyFile").optional(true)
        inputs.files(pmdCpdRuntime).withPropertyName("pmdClasspath")
        inputs.property("cpdMode", configuredMode)
        inputs.property("qualityChangedFiles", changedFilesJson ?: "<missing>")
        inputs.files(productionSourceDirs.map { dir ->
            fileTree(dir).matching { include("**/*.java") }
        }).withPropertyName("sourceFiles").optional(true)
        outputs.dir(reportDir).withPropertyName("reportDir")
        outputs.dir(workDir).withPropertyName("workDir")
        doLast(
            ReuseStandardCpdAction(
                rootPath,
                policyFileRef.absolutePath,
                reportDir.absolutePath,
                workDir.absolutePath,
                configuredMode,
                changedFilesJson,
                sourceDirPaths,
                pmdClasspathEntries,
            )
        )
    }

}
