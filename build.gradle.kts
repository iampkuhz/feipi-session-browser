plugins {
    base
    jacoco
}

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

// ============================================================
// verifyChineseJavaComments —— 全量扫描项目自有 Java 源码注释。
// 配置缓存兼容：动作逻辑提取到顶层函数。
// ============================================================
val verifyChineseJavaComments = tasks.register("verifyChineseJavaComments") {
    group = "verification"
    description = "扫描项目自有 Java 源码注释，验证中文为主体、术语允许英文。"

    val checkerScript = file("scripts/quality/check_code_comment_language.py")
    val policyFile = file("config/technical-terms.json")
    val cacheFile = layout.buildDirectory.file("reports/chinese-comments/cache.json")
    val reportDir = layout.buildDirectory.dir("reports/chinese-comments")

    // 声明脚本和策略文件为 inputs。
    inputs.files(checkerScript, policyFile)
    // 声明所有 Java/Kotlin/Gradle 源文件为 inputs：源文件变化时 task 必须重新执行。
    // 排除 build 输出目录，避免与其他 task 的输出产生隐式依赖。
    inputs.files(
        fileTree("java").apply {
            include("**/*.java")
            exclude("**/build/**")
        },
        fileTree("build-logic").apply {
            include("**/*.java", "**/*.kt", "**/*.kts")
            exclude("**/build/**", "**/.gradle/**")
        },
    ).withPropertyName("sourceFiles")
    inputs.file("build.gradle.kts").withPropertyName("rootBuildScript")
    inputs.file("settings.gradle.kts").withPropertyName("settingsScript")
    // 声明输出文件，使 task 可被 up-to-date 检查。
    outputs.file(cacheFile)
    outputs.file(layout.buildDirectory.file("reports/chinese-comments/report.json"))

    // 配置时解析所有路径为绝对路径字符串，避免执行时引用脚本对象。
    val scriptPath = checkerScript.absolutePath
    val policyPath = policyFile.absolutePath
    val cachePath = cacheFile.get().asFile.absolutePath
    val reportPath = reportDir.get().asFile.absolutePath

    doLast(runChineseCommentCheckAction(scriptPath, policyPath, cachePath, reportPath))
}

// ============================================================
// verifyChineseJavaCommentsChanged —— 仅扫描变更文件的快速检查。
// ============================================================
val verifyChineseJavaCommentsChanged = tasks.register("verifyChineseJavaCommentsChanged") {
    group = "verification"
    description = "仅扫描 Git changed Java 文件的中文注释。"

    val checkerScript = file("scripts/quality/check_code_comment_language.py")
    val policyFile = file("config/technical-terms.json")
    val changedFilesJson = layout.buildDirectory.file("tmp/changed-java-files.json")
    val reportDir = layout.buildDirectory.dir("reports/chinese-comments-changed")

    inputs.files(checkerScript, policyFile)
    // 声明输出文件，使 task 可被 up-to-date 检查（注意：git diff 本身不可复现）。
    outputs.file(layout.buildDirectory.file("reports/chinese-comments-changed/report.json"))
        .withPropertyName("reportFile")

    // 配置时解析路径，避免执行时引用脚本对象。
    val scriptPath = checkerScript.absolutePath
    val policyPath = policyFile.absolutePath
    val changedFilesPath = changedFilesJson.get().asFile.absolutePath
    val reportPath = reportDir.get().asFile.absolutePath

    doLast(runChineseCommentCheckChangedAction(scriptPath, policyPath, changedFilesPath, reportPath))
}

tasks.named("check") {
    dependsOn(verifyChineseJavaComments)
}

// ============================================================
// verifyJavaRecordComponentJavadocs —— 校验 record component 中文 Javadoc。
// 已迁移到 Java 实现 :java:tests:quality-gates:verifyJavaRecordComponentJavadocs。
// ============================================================
val verifyJavaRecordComponentJavadocs = tasks.register("verifyJavaRecordComponentJavadocs") {
    group = "verification"
    description = "Verifies every Java record component has a Chinese @param Javadoc entry."
    dependsOn(":java:tests:quality-gates:verifyJavaRecordComponentJavadocs")
}

tasks.named("check") {
    dependsOn(verifyJavaRecordComponentJavadocs)
}

// ============================================================
// verifyJavaApiSnapshot —— 校验 Java public API 基线。
// ============================================================
val verifyJavaApiSnapshot = tasks.register<Exec>("verifyJavaApiSnapshot") {
    group = "verification"
    description = "Verifies that current Java public API matches the approved snapshot."

    val checkerScript = file("scripts/quality/check_java_api_snapshot.py")
    val snapshotFile = file("config/api-snapshots/java-public-api.txt")
    val reportFile = layout.buildDirectory.file("reports/java-api-snapshot/result.txt")

    inputs.file(checkerScript).withPropertyName("checkerScript")
    inputs.file(snapshotFile).withPropertyName("apiSnapshot")
    inputs.files(
        fileTree("java").apply {
            include("**/src/main/java/**/*.java")
            exclude("**/build/**")
        },
    ).withPropertyName("javaSourceFiles")
    outputs.file(reportFile).withPropertyName("resultFile")

    commandLine(
        "python3",
        checkerScript.absolutePath,
        "--check",
        "--java-root",
        file("java").absolutePath,
        "--snapshot",
        snapshotFile.absolutePath,
    )
    doLast {
        val result = reportFile.get().asFile
        result.parentFile.mkdirs()
        result.writeText("PASSED\n", Charsets.UTF_8)
    }
}

tasks.named("check") {
    dependsOn(verifyJavaApiSnapshot)
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

/**
 * verifyChineseJavaComments 的执行动作。
 * 调用中文注释检查脚本对全量 Java 源文件进行扫描。
 */
private fun runChineseCommentCheckAction(
    scriptPath: String,
    policyPath: String,
    cachePath: String,
    reportDirPath: String,
): org.gradle.api.Action<Task> {
    return org.gradle.api.Action<Task> {
        val reportDir = java.io.File(reportDirPath)
        reportDir.mkdirs()
        val reportFile = java.io.File(reportDir, "report.json")
        val cmd = listOf(
            "python3", scriptPath,
            "java", "build-logic", "build.gradle.kts", "settings.gradle.kts",
            "--policy", policyPath,
            "--json-report", reportFile.absolutePath,
            "--cache", cachePath,
        )
        val pb = ProcessBuilder(cmd).inheritIO()
        val process = pb.start()
        val exitCode = process.waitFor()
        if (exitCode != 0) {
            throw org.gradle.api.GradleException(
                "verifyChineseJavaComments: 中文注释检查失败（exit=$exitCode），详见 ${reportFile.absolutePath}"
            )
        }
        logger.lifecycle("verifyChineseJavaComments: PASSED – 全部 Java 注释通过中文近似检查。")
    }
}

/**
 * verifyChineseJavaCommentsChanged 的执行动作。
 * 仅扫描 Git 变更的 Java 文件的中文注释。
 */
private fun runChineseCommentCheckChangedAction(
    scriptPath: String,
    policyPath: String,
    changedFilesJsonPath: String,
    reportDirPath: String,
): org.gradle.api.Action<Task> {
    return org.gradle.api.Action<Task> {
        val changedFiles = try {
            val proc = ProcessBuilder("git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD")
                .redirectErrorStream(true).start()
            proc.inputStream.bufferedReader().readLines().filter { it.endsWith(".java") }
        } catch (e: Exception) {
            logger.lifecycle("verifyChineseJavaCommentsChanged: 无法获取 changed files，回退到全量扫描。")
            null
        }
        if (changedFiles != null && changedFiles.isEmpty()) {
            logger.lifecycle("verifyChineseJavaCommentsChanged: 无 Java 文件变更，跳过。")
            return@Action
        }
        val filesJson = changedFiles?.joinToString(",") { "\"$it\"" }
        val filesFrom = if (filesJson != null) {
            val tmpFile = java.io.File(changedFilesJsonPath)
            tmpFile.parentFile.mkdirs()
            tmpFile.writeText("[$filesJson]", Charsets.UTF_8)
            tmpFile
        } else null

        val reportDir = java.io.File(reportDirPath)
        reportDir.mkdirs()
        val reportFile = java.io.File(reportDir, "report.json")

        val cmd = mutableListOf(
            "python3", scriptPath,
            "java", "build-logic",
            "--policy", policyPath,
            "--json-report", reportFile.absolutePath,
        )
        if (filesFrom != null) {
            cmd.addAll(listOf("--files-from", filesFrom.absolutePath))
        }
        val pb = ProcessBuilder(cmd).inheritIO()
        val process = pb.start()
        val exitCode = process.waitFor()
        if (exitCode != 0) {
            throw org.gradle.api.GradleException(
                "verifyChineseJavaCommentsChanged: 中文注释检查失败（exit=$exitCode），详见 ${reportFile.absolutePath}"
            )
        }
        logger.lifecycle("verifyChineseJavaCommentsChanged: PASSED")
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

data class ReuseCpdProfile(
    val id: String,
    val minimumTokens: Int,
    val ignoreAnnotations: Boolean,
    val ignoreLiterals: Boolean,
    val ignoreIdentifiers: Boolean,
    val skipDuplicateFiles: Boolean,
    val scope: String,
)

fun reuseBoolean(value: Any?, defaultValue: Boolean): Boolean =
    if (value is Boolean) value else defaultValue

fun reuseInt(value: Any?, defaultValue: Int): Int =
    if (value is Number) value.toInt() else defaultValue

fun reuseString(value: Any?, defaultValue: String): String =
    if (value is String && value.isNotBlank()) value else defaultValue

fun sanitizeReuseProfileId(value: String): String =
    value.replace(Regex("[^A-Za-z0-9._-]"), "-").ifBlank { "profile" }

fun loadReuseCpdProfiles(policyFile: File): List<ReuseCpdProfile> {
    val defaultProfile = ReuseCpdProfile(
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
    val base = ReuseCpdProfile(
        id = reuseString(standard["id"], defaultProfile.id),
        minimumTokens = reuseInt(standard["minimumTokens"], defaultProfile.minimumTokens),
        ignoreAnnotations = reuseBoolean(standard["ignoreAnnotations"], defaultProfile.ignoreAnnotations),
        ignoreLiterals = reuseBoolean(standard["ignoreLiterals"], defaultProfile.ignoreLiterals),
        ignoreIdentifiers = reuseBoolean(standard["ignoreIdentifiers"], defaultProfile.ignoreIdentifiers),
        skipDuplicateFiles = reuseBoolean(standard["skipDuplicateFiles"], defaultProfile.skipDuplicateFiles),
        scope = reuseString(standard["scope"], defaultProfile.scope),
    )
    val rawProfiles = standard["profiles"] as? List<*> ?: return listOf(base)
    val profiles = rawProfiles.mapIndexedNotNull { index, raw ->
        val profile = raw as? Map<*, *> ?: return@mapIndexedNotNull null
        ReuseCpdProfile(
            id = sanitizeReuseProfileId(reuseString(profile["id"], "profile-${index + 1}")),
            minimumTokens = reuseInt(profile["minimumTokens"], base.minimumTokens),
            ignoreAnnotations = reuseBoolean(profile["ignoreAnnotations"], base.ignoreAnnotations),
            ignoreLiterals = reuseBoolean(profile["ignoreLiterals"], base.ignoreLiterals),
            ignoreIdentifiers = reuseBoolean(profile["ignoreIdentifiers"], base.ignoreIdentifiers),
            skipDuplicateFiles = reuseBoolean(profile["skipDuplicateFiles"], base.skipDuplicateFiles),
            scope = reuseString(profile["scope"], base.scope),
        )
    }
    return profiles.ifEmpty { listOf(base) }
}

fun reuseCpdArgs(profile: ReuseCpdProfile, sourceDirs: List<File>, reportFile: File, root: File): List<String> =
    buildList {
        add("cpd")
        add("--language")
        add("java")
        add("--minimum-tokens")
        add(profile.minimumTokens.toString())
        if (profile.skipDuplicateFiles) {
            add("--skip-duplicate-files")
        }
        if (profile.ignoreAnnotations) {
            add("--ignore-annotations")
        }
        if (profile.ignoreLiterals) {
            add("--ignore-literals")
        }
        if (profile.ignoreIdentifiers) {
            add("--ignore-identifiers")
        }
        add("--format")
        add("xml")
        add("--report-file")
        add(reportFile.absolutePath)
        add("--relativize-paths-with")
        add(root.absolutePath)
        add("--dir")
        add(sourceDirs.joinToString(",") { it.absolutePath })
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
        inputs.file(policyFileRef).withPropertyName("policyFile").optional(true)
        inputs.files(productionSourceDirs.map { dir ->
            fileTree(dir).matching { include("**/*.java") }
        }).withPropertyName("sourceFiles").optional(true)
        outputs.dir(reportDir).withPropertyName("reportDir")
        notCompatibleWithConfigurationCache("PMD CPD CLI is launched as external processes")

        doLast {
            val sourceDirs = productionSourceDirs.filter { it.isDirectory }
            reportDir.mkdirs()
            if (sourceDirs.isEmpty()) {
                logger.lifecycle("reuseStandardCpd: no Java production source dirs")
                return@doLast
            }
            val profiles = loadReuseCpdProfiles(policyFileRef)
            val failures = mutableListOf<String>()
            val javaExecutable = File(System.getProperty("java.home"), "bin/java").absolutePath
            val pmdClasspath = pmdCpdRuntime.resolve().joinToString(File.pathSeparator) { it.absolutePath }
            val sourceFiles = sourceDirs.flatMap { dir ->
                dir.walkTopDown().filter { it.isFile && it.extension == "java" }.toList()
            }

            fun runCpd(profile: ReuseCpdProfile, inputs: List<File>, reportFile: File): Int {
                reportFile.parentFile.mkdirs()
                val command = listOf(
                    javaExecutable,
                    "-cp",
                    pmdClasspath,
                    "net.sourceforge.pmd.cli.PmdCli",
                ) + reuseCpdArgs(profile, inputs, reportFile, rootDir)
                val process = ProcessBuilder(command)
                    .directory(rootDir)
                    .inheritIO()
                    .start()
                return process.waitFor()
            }

            profiles.forEach { profile ->
                if (profile.scope == "same-file") {
                    sourceFiles.forEach { sourceFile ->
                        val relative = rootDir.toPath().relativize(sourceFile.toPath()).toString()
                        val reportName = sanitizeReuseProfileId(relative) + ".xml"
                        val reportFile = reportDir.resolve("cpd-${profile.id}").resolve(reportName)
                        val exitValue = runCpd(profile, listOf(sourceFile), reportFile)
                        if (exitValue != 0) {
                            failures.add(
                                "${profile.id}:${relative}(exit=$exitValue, report=${reportFile.absolutePath})"
                            )
                        }
                    }
                } else {
                    val reportFile = reportDir.resolve("cpd-${profile.id}.xml")
                    val exitValue = runCpd(profile, sourceDirs, reportFile)
                    if (exitValue != 0) {
                        failures.add("${profile.id}(exit=$exitValue, report=${reportFile.absolutePath})")
                    }
                }
            }
            val summaryFile = reportDir.resolve("standard-cpd-summary.json")
            val profileJson = profiles.joinToString(", ") { "\"${it.id}\"" }
            val reportsJson = reportDir.absolutePath.replace("\\", "\\\\").replace("\"", "\\\"")
            summaryFile.writeText(
                "{\n" +
                    "  \"engine\": \"PMD_CPD_CLI\",\n" +
                    "  \"status\": \"${if (failures.isEmpty()) "PASS" else "FAIL"}\",\n" +
                    "  \"profiles\": [$profileJson],\n" +
                    "  \"reports\": \"$reportsJson\"\n" +
                    "}\n",
                Charsets.UTF_8,
            )
            if (failures.isNotEmpty()) {
                throw org.gradle.api.GradleException("PMD CPD duplicate violations: ${failures.joinToString(", ")}")
            }
            logger.lifecycle("reuseStandardCpd: PMD CPD PASS (${profiles.size} profile(s))")
        }
    }

    tasks.register("reuseAnalyzeIncremental") {
        group = "verification"
        description = "复用语义规则已迁移到 PMD；运行所有 pmdMain 作为增量复用门禁。"
        val pmdTasks = subprojects.mapNotNull { sub -> sub.tasks.findByName("pmdMain") }
        dependsOn(pmdTasks)
        val outputFile = reuseAnalysisReportDir.get().file("incremental-result.json").asFile
        outputs.file(outputFile).withPropertyName("resultFile")
        doLast {
            outputFile.parentFile.mkdirs()
            outputFile.writeText("""{
  "schemaVersion": 1,
  "status": "PASS",
  "findings": [],
  "metadata": {
    "engine": "PMD",
    "delegatedTo": "pmdMain"
  }
}
""", Charsets.UTF_8)
            logger.lifecycle("reuseAnalyzeIncremental: delegated to PMD pmdMain")
        }
    }
}
