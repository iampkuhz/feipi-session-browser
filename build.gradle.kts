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

        // 配置时解析所有测试目录路径为字符串列表，避免执行时引用脚本对象。
        val testDirs: List<String> = leafSubprojects.map { sub ->
            sub.layout.buildDirectory.dir("test-results/test").get().asFile.absolutePath
        }
        // 声明测试目录为 inputs，确保 up-to-date 检查正确。
        inputs.files(testDirs).withPropertyName("testResultDirs")
            .optional(true)
        outputs.file(layout.buildDirectory.file("reports/verify-no-skipped-tests/result.txt"))
            .withPropertyName("resultFile")
        doLast(checkNoSkippedTestsAction(testDirs, layout.buildDirectory.file("reports/verify-no-skipped-tests/result.txt").get().asFile.absolutePath))
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

    inputs.files(checkerScript, policyFile)
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
    testResultDirs: List<String>,
    resultFilePath: String = "",
): org.gradle.api.Action<Task> {
    return org.gradle.api.Action<Task> {
        var totalSkipped = 0
        var totalErrors = 0
        var totalTests = 0
        var filesFound = 0

        testResultDirs.forEach { dirPath ->
            val testResultsDir = java.io.File(dirPath)
            if (testResultsDir.exists()) {
                testResultsDir.walkTopDown()
                    .filter { it.name.startsWith("TEST-") && it.extension == "xml" }
                    .forEach { file ->
                        filesFound++
                        val content = file.readText()
                        val skippedMatch = Regex("""skipped="(\d+)"""").find(content)
                        val errorsMatch = Regex("""errors="(\d+)"""").find(content)
                        val testsMatch = Regex("""tests="(\d+)"""").find(content)
                        totalSkipped += skippedMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        totalErrors += errorsMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        totalTests += testsMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                    }
            }
        }

        if (totalSkipped > 0) {
            throw org.gradle.api.GradleException(
                "Found $totalSkipped skipped test(s). Skipped tests are not allowed."
            )
        }
        if (totalErrors > 0) {
            throw org.gradle.api.GradleException(
                "Found $totalErrors aborted/errored test(s). Aborted tests are not allowed."
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
                    "0 skipped, 0 aborted."
            )
        }
        if (resultFilePath.isNotEmpty()) {
            val resultFile = java.io.File(resultFilePath)
            resultFile.parentFile.mkdirs()
            resultFile.writeText("$totalTests tests in $filesFound files, 0 skipped, 0 aborted.\n", Charsets.UTF_8)
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
