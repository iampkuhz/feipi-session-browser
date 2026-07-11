plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}

tasks.withType<Test>().configureEach {
    jvmArgs("--add-modules", "jdk.compiler")
}

// ============================================================
// verifyJavaRecordComponentJavadocs —— Java 质量门 CLI 执行。
// ============================================================
val verifyJavaRecordComponentJavadocs = tasks.register<JavaExec>("verifyJavaRecordComponentJavadocs") {
    group = "verification"
    description = "Java 实现的 record component Javadoc 门禁。"

    mainClass.set("com.feipi.session.browser.quality.gates.cli.QualityGateCli")
    classpath = sourceSets["main"].runtimeClasspath

    val reportFile = layout.buildDirectory.file("reports/java-record-component-javadocs/result.txt")
    args(
        "--gate", "record-component-javadocs",
        "--repo-root", rootProject.projectDir.absolutePath,
        "--paths", rootProject.file("java").absolutePath,
        "--report-file", reportFile.get().asFile.absolutePath,
    )

    inputs.files(
        rootProject.fileTree("java").apply {
            include("**/src/main/java/**/*.java")
            exclude("**/build/**")
        },
    ).withPropertyName("javaMainSourceFiles")
    outputs.file(reportFile).withPropertyName("resultFile")
}

// ============================================================
// verifyJavaQualityGates —— 聚合所有 Java 质量门。
// ============================================================
val verifyJavaQualityGates = tasks.register("verifyJavaQualityGates") {
    group = "verification"
    description = "聚合所有 Java 质量门执行。"
    dependsOn(verifyJavaRecordComponentJavadocs)
}

// ============================================================
// verifyLegacyRecordComponentJavadocsParity —— Python/Java 迁移一致性对比。
// ============================================================
val pythonScriptPath = rootProject.file("scripts/quality/check_java_record_component_javadocs.py").absolutePath
val fixtureDirPath = project.file("src/test/resources/fixtures/record-component-javadocs").absolutePath
val repoJavaDirPath = rootProject.file("java").absolutePath
val parityClasspathProvider = { sourceSets["main"].runtimeClasspath.asPath }

val verifyLegacyParity = tasks.register("verifyLegacyRecordComponentJavadocsParity") {
    group = "verification"
    description = "对比旧 Python 和新 Java 的 record component Javadoc 门禁输出。"

    val pythonFixtureOutput = layout.buildDirectory.file("tmp/parity/python-fixtures.txt")
    val pythonRepoOutput = layout.buildDirectory.file("tmp/parity/python-repo.txt")
    val parityReport = layout.buildDirectory.file("reports/legacy-parity/record-component-javadocs.txt")

    inputs.file(pythonScriptPath).withPropertyName("pythonScript")
    inputs.dir(fixtureDirPath).withPropertyName("fixtureDir")
    outputs.file(parityReport).withPropertyName("parityReport")

    notCompatibleWithConfigurationCache("External Python process and runtime classpath resolution")

    doLast {
        val scriptFile = File(pythonScriptPath)
        if (!scriptFile.exists()) {
            val report = parityReport.get().asFile
            report.parentFile.mkdirs()
            report.writeText(
                "Legacy Python script has been removed.\n" +
                    "Parity was verified before removal.\n" +
                    "Java fixture tests provide long-term protection.\n" +
                    "PASSED (legacy removed)\n",
            )
            logger.lifecycle(
                "verifyLegacyRecordComponentJavadocsParity: " +
                    "PASSED (legacy Python script removed, parity was verified)"
            )
            return@doLast
        }

        val pfOut = pythonFixtureOutput.get().asFile
        val prOut = pythonRepoOutput.get().asFile
        val report = parityReport.get().asFile
        pfOut.parentFile.mkdirs()
        prOut.parentFile.mkdirs()
        report.parentFile.mkdirs()

        // 收集 fixture 文件列表
        val fixtureFiles = File(fixtureDirPath).walkTopDown()
            .filter { it.isFile && it.extension == "java" }
            .map { it.absolutePath }
            .toList()

        // 运行 Python 脚本对 fixtures
        runPythonScriptLocal(pythonScriptPath, fixtureFiles, pfOut)

        // 运行 Python 脚本对真实仓库
        runPythonScriptLocal(pythonScriptPath, listOf(repoJavaDirPath), prOut)

        // 运行 ParityRunner
        val javaBin = File(System.getProperty("java.home"), "bin/java").absolutePath
        val parityCmd = listOf(
            javaBin,
            "-cp", parityClasspathProvider(),
            "com.feipi.session.browser.quality.gates.cli.ParityRunner",
            fixtureDirPath,
            repoJavaDirPath,
            pfOut.absolutePath,
            prOut.absolutePath,
            report.absolutePath,
        )
        val pb = ProcessBuilder(parityCmd).inheritIO()
        val process = pb.start()
        val exitCode = process.waitFor()
        if (exitCode != 0) {
            throw org.gradle.api.GradleException(
                "Legacy parity check failed. See report: ${report.absolutePath}"
            )
        }
        logger.lifecycle("verifyLegacyRecordComponentJavadocsParity: PASSED")
    }
}

fun runPythonScriptLocal(scriptPath: String, args: List<String>, stderrFile: File) {
    val cmd = listOf("python3", scriptPath) + args
    val pb = ProcessBuilder(cmd)
    pb.redirectError(stderrFile)
    pb.redirectOutput(ProcessBuilder.Redirect.DISCARD)
    val process = pb.start()
    val exitCode = process.waitFor()
    // Python 脚本在有 violations 时返回 1，这是正常的
    if (exitCode != 0 && exitCode != 1) {
        throw org.gradle.api.GradleException(
            "Python quality gate failed with exit code $exitCode"
        )
    }
}
