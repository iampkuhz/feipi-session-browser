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

// ============================================================
// Reuse Analyzer 任务 —— Spoon AST 分析。
// 这些任务使用 java:reuse-analyzer 模块的 classpath 运行分析器。
// Spoon 仅作为构建期工具，不进入产品 runtime。
// ============================================================

// 分析器 classpath 配置
val analyzerRuntime = configurations.create("analyzerRuntime") {
    isCanBeConsumed = false
    isCanBeResolved = true
}

dependencies {
    add("analyzerRuntime", project(":java:reuse-analyzer"))
}

// 分析器缓存目录（local state，不提交）
val reuseAnalysisCacheDir = layout.projectDirectory.dir(".gradle/feipi-reuse-analysis")
val reuseAnalysisReportDir = layout.buildDirectory.dir("reports/reuse-analysis")

// 策略和 schema 文件路径
val policyFilePath = file("config/reuse-analysis/policy.json").absolutePath
val bootstrapStatePath = file("config/reuse-analysis/bootstrap-state.json").absolutePath

// ============================================================
// reuseAnalyzerSelfTest —— 分析器自测。
// ============================================================
val reuseAnalyzerSelfTest = tasks.register<JavaExec>("reuseAnalyzerSelfTest") {
    group = "verification"
    description = "验证 Spoon analyzer 自测通过。"
    classpath = analyzerRuntime
    mainClass.set("com.feipi.session.browser.reuse.analyzer.AnalyzerMain")
    args(
        "--mode", "selftest",
        "--cache-dir", reuseAnalysisCacheDir.asFile.absolutePath,
        "--output", reuseAnalysisReportDir.get().file("selftest-result.json").asFile.absolutePath,
    )
    outputs.file(reuseAnalysisReportDir.get().file("selftest-result.json"))
        .withPropertyName("resultFile")
}

// ============================================================
// JSON 辅助函数 —— 根构建脚本不使用 Jackson，手动构造 JSON。
// ============================================================
fun escapeJsonString(s: String): String {
    return s.replace("\\", "\\\\")
        .replace("\"", "\\\"")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
}

fun jsonArrayOfStrings(items: List<String>): String {
    return "[" + items.joinToString(", ") { "\"${escapeJsonString(it)}\"" } + "]"
}

// ============================================================
// 生成分析器输入清单。
// 每个生产模块在自身项目中解析 compileClasspath（避免跨项目配置解析限制），
// 由根任务聚合各模块信息生成最终清单。
// ============================================================
gradle.projectsEvaluated {
    val productionModules = leafSubprojects.filter { sub ->
        sub.path != ":java:reuse-analyzer"
            && sub.path != ":java:test-support"
            && sub.path != ":java:architecture-tests"
            && sub.path != ":java:contract-tests"
            && sub.file("src/main/java").exists()
    }

    // --------------------------------------------------------
    // 为每个生产模块注册 classpath 信息收集任务。
    // 任务在子项目内解析自身的 compileClasspath，输出 JSON。
    // 配置缓存兼容：doLast 内不调用脚本级函数，不捕获 Project 引用。
    // --------------------------------------------------------
    val classpathInfoTasks = productionModules.map { sub ->
        val modulePath = sub.path
        val sourceRootPath = sub.file("src/main/java").absolutePath
        val cpFiles: FileCollection = files(sub.configurations.getByName("compileClasspath"))
        val outputDirPath = sub.layout.buildDirectory.dir("classes/java/main").get().asFile.absolutePath
        val infoFile = layout.buildDirectory.get().asFile
            .resolve("reports/reuse-analysis/classpath-info")
            .resolve(modulePath.removePrefix(":").replace(":", "-") + ".json")

        sub.tasks.register("reuseClasspathInfo") {
            group = "verification"
            description = "收集 ${modulePath} 的 classpath 信息供 reuse analyzer 使用。"

            inputs.files(cpFiles).withPropertyName("classpathFiles").optional(true)
            outputs.file(infoFile).withPropertyName("classpathInfoFile")

            doLast {
                val resolvedCp = cpFiles.files.map { it.absolutePath }.sorted()
                // Inline JSON helpers to avoid capturing the build-script object.
                fun esc(s: String) = s.replace("\\", "\\\\").replace("\"", "\\\"")
                    .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
                fun jsonArr(items: List<String>) =
                    "[" + items.joinToString(", ") { "\"${esc(it)}\"" } + "]"
                val json = """{
  "id": "${esc(modulePath)}",
  "productionSourceRoots": ${jsonArr(listOf(sourceRootPath))},
  "compileClasspath": ${jsonArr(resolvedCp)},
  "compiledOutputs": ${jsonArr(listOf(outputDirPath))}
}
"""
                infoFile.parentFile.mkdirs()
                infoFile.writeText(json, Charsets.UTF_8)
            }
        }
    }

    // --------------------------------------------------------
    // reuseGenerateManifest —— 聚合各模块 classpath 信息，生成输入清单。
    // 配置缓存兼容：预计算所有 File 路径，doLast 内仅使用 String/File/List。
    // --------------------------------------------------------
    val moduleInfoFiles = productionModules.map { sub ->
        val modulePath = sub.path
        layout.buildDirectory.get().asFile
            .resolve("reports/reuse-analysis/classpath-info")
            .resolve(modulePath.removePrefix(":").replace(":", "-") + ".json")
    }

    val generateManifest = tasks.register("reuseGenerateManifest") {
        group = "verification"
        description = "生成 reuse analyzer 输入清单 JSON。"

        val manifestFile = reuseAnalysisReportDir.get().file("input-manifest.json").asFile
        val rootDirPath = rootDir.absolutePath
        val policyFileRef = file(policyFilePath)
        val srcDirPaths = productionModules.map { it.file("src/main/java").absolutePath }

        dependsOn(classpathInfoTasks)

        // 声明 inputs
        inputs.files(srcDirPaths.map { path ->
            fileTree(path).matching { include("**/*.java") }
        }).withPropertyName("sourceFiles").optional(true)
        if (policyFileRef.exists()) {
            inputs.file(policyFileRef).withPropertyName("policyFile")
        }

        // 声明 outputs
        outputs.file(manifestFile).withPropertyName("manifestFile")

        doLast {
            // 读取各模块 classpath 信息（使用预计算的 File 列表，不访问 Task 引用）
            val moduleJsons = moduleInfoFiles.map { f ->
                f.readText(Charsets.UTF_8).trim()
            }

            // git changed files（执行时，非配置时）
            val changedFiles = try {
                val proc = ProcessBuilder("git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD")
                    .directory(File(rootDirPath)).redirectErrorStream(true).start()
                proc.inputStream.bufferedReader().readLines().filter { it.endsWith(".java") }
            } catch (e: Exception) {
                emptyList<String>()
            }

            val baseSha = try {
                ProcessBuilder("git", "rev-parse", "HEAD").directory(File(rootDirPath))
                    .redirectErrorStream(true).start()
                    .inputStream.bufferedReader().readText().trim()
            } catch (e: Exception) { "unknown" }

            val policyDigest = if (policyFileRef.exists()) {
                val digest = java.security.MessageDigest.getInstance("SHA-256")
                val hash = digest.digest(policyFileRef.readBytes())
                hash.joinToString("") { "%02x".format(it) }
            } else "0000000000000000000000000000000000000000000000000000000000000000"

            // Inline JSON helpers to avoid capturing the build-script object.
            fun esc(s: String) = s.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
            fun jsonArr(items: List<String>) =
                "[" + items.joinToString(", ") { "\"${esc(it)}\"" } + "]"

            val json = """{
  "javaVersion": 25,
  "modules": [
${moduleJsons.joinToString(",\n")}
  ],
  "changedFiles": ${jsonArr(changedFiles.sorted())},
  "baseSha": "${esc(baseSha)}",
  "policyDigest": "$policyDigest"
}
"""
            manifestFile.parentFile.mkdirs()
            manifestFile.writeText(json, Charsets.UTF_8)
            logger.lifecycle("输入清单已生成：${manifestFile.absolutePath}")
        }
    }

    // ============================================================
    // reuseBootstrapFull —— 全量引导分析。
    // ============================================================
    tasks.register<JavaExec>("reuseBootstrapFull") {
        group = "verification"
        description = "执行全量 bootstrap 分析，构建完整 fingerprint 索引。"
        dependsOn(generateManifest)
        classpath = analyzerRuntime
        mainClass.set("com.feipi.session.browser.reuse.analyzer.AnalyzerMain")
        val manifestFile = reuseAnalysisReportDir.get().file("input-manifest.json").asFile.absolutePath
        val outputFile = reuseAnalysisReportDir.get().file("bootstrap-full-result.json").asFile.absolutePath
        args(
            "--mode", "full",
            "--manifest", manifestFile,
            "--cache-dir", reuseAnalysisCacheDir.asFile.absolutePath,
            "--output", outputFile,
        )
        inputs.file(manifestFile).withPropertyName("manifest")
        outputs.file(outputFile).withPropertyName("resultFile")
        // Bootstrap 模式仅构建索引，发现不阻断构建。
        isIgnoreExitValue = true
    }

    // ============================================================
    // reuseAnalyzeIncremental —— 增量分析。
    // 当 bootstrap state 不存在时返回 BOOTSTRAP_REQUIRED。
    // ============================================================
    tasks.register<JavaExec>("reuseAnalyzeIncremental") {
        group = "verification"
        description = "增量分析：只分析 changed files，无 bootstrap state 时返回 BOOTSTRAP_REQUIRED。"
        dependsOn(generateManifest)
        classpath = analyzerRuntime
        mainClass.set("com.feipi.session.browser.reuse.analyzer.AnalyzerMain")
        val manifestFile = reuseAnalysisReportDir.get().file("input-manifest.json").asFile.absolutePath
        val outputFile = reuseAnalysisReportDir.get().file("incremental-result.json").asFile.absolutePath
        args(
            "--mode", "incremental",
            "--manifest", manifestFile,
            "--cache-dir", reuseAnalysisCacheDir.asFile.absolutePath,
            "--bootstrap-state", bootstrapStatePath,
            "--output", outputFile,
        )
        inputs.file(manifestFile).withPropertyName("manifest")
        outputs.file(outputFile).withPropertyName("resultFile")
    }

    // ============================================================
    // reuseAnalyzeFullAdvisory —— 全量 advisory 分析（不阻断）。
    // ============================================================
    tasks.register<JavaExec>("reuseAnalyzeFullAdvisory") {
        group = "verification"
        description = "全量 advisory 分析，生成报告但不阻断构建。"
        dependsOn(generateManifest)
        classpath = analyzerRuntime
        mainClass.set("com.feipi.session.browser.reuse.analyzer.AnalyzerMain")
        val manifestFile = reuseAnalysisReportDir.get().file("input-manifest.json").asFile.absolutePath
        val outputFile = reuseAnalysisReportDir.get().file("full-advisory-result.json").asFile.absolutePath
        args(
            "--mode", "full",
            "--manifest", manifestFile,
            "--cache-dir", reuseAnalysisCacheDir.asFile.absolutePath,
            "--output", outputFile,
        )
        inputs.file(manifestFile).withPropertyName("manifest")
        outputs.file(outputFile).withPropertyName("resultFile")
        // advisory：失败不阻断
        isIgnoreExitValue = true
    }

    // ============================================================
    // reuseBaselineVerify —— baseline 验证。
    // ============================================================
    val baselineFilePath = file("config/reuse-analysis/baseline.json").absolutePath
    tasks.register<JavaExec>("reuseBaselineVerify") {
        group = "verification"
        description = "验证 baseline 与新 finding 的一致性。"
        dependsOn(generateManifest)
        classpath = analyzerRuntime
        mainClass.set("com.feipi.session.browser.reuse.analyzer.AnalyzerMain")
        val manifestFile = reuseAnalysisReportDir.get().file("input-manifest.json").asFile.absolutePath
        val outputFile = reuseAnalysisReportDir.get().file("baseline-verify-result.json").asFile.absolutePath
        args(
            "--mode", "baseline",
            "--manifest", manifestFile,
            "--cache-dir", reuseAnalysisCacheDir.asFile.absolutePath,
            "--baseline-file", baselineFilePath,
            "--output", outputFile,
        )
        inputs.file(manifestFile).withPropertyName("manifest")
        outputs.file(outputFile).withPropertyName("resultFile")
    }
}
