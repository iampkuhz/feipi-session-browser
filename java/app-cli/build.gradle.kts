import java.time.Instant

plugins {
    id("feipi.java-application")
    id("feipi.java-test")
}

application {
    mainClass.set("com.feipi.session.browser.cli.App")
}

dependencies {
    implementation(project(":java:core-domain"))
    implementation(project(":java:source-spi"))
    implementation(project(":java:source-json"))
    implementation(project(":java:source-claude"))
    implementation(project(":java:source-codex"))
    implementation(project(":java:source-qoder"))
    implementation(project(":java:normalization-engine"))
    implementation(project(":java:artifact-normalized"))
    implementation(libs.picocli)
    implementation(libs.bundles.jackson)

    testImplementation(project(":java:test-support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}

// ============================================================
// build-info.properties 生成
// git commit 和 build timestamp 通过环境变量可覆盖，确保相同输入可复现。
// ============================================================
val generateBuildInfo = tasks.register("generateBuildInfo") {
    val versionFile = rootProject.file("VERSION")
    val projectDirFile = rootProject.projectDir
    val outputDir = layout.buildDirectory.dir("generated/build-info")

    // 通过环境变量提供可复现输入；相同输入时 distribution 可复现。
    val gitCommitProvider = providers.environmentVariable("BUILD_GIT_COMMIT")
        .orElse(
            providers.exec {
                commandLine("git", "rev-parse", "--short=12", "HEAD")
                workingDir(projectDirFile)
            }.standardOutput.asText.map { it.trim() }
                .orElse(providers.provider { "unknown" })
        )
    val buildTimestampProvider = providers.environmentVariable("BUILD_TIMESTAMP")
        .orElse(providers.provider { Instant.now().toString() })

    inputs.file(versionFile)
    inputs.property("gitCommit", gitCommitProvider)
    inputs.property("buildTimestamp", buildTimestampProvider)
    outputs.dir(outputDir)

    val gitCommitValue = gitCommitProvider.get()
    val buildTimestampValue = buildTimestampProvider.get()

    doLast {
        val version = versionFile.readText().trim()
        val propsDir = outputDir.get().asFile.resolve("com/feipi/session/browser/cli")
        propsDir.mkdirs()
        propsDir.resolve("build-info.properties").writeText(
            "app.version=$version\n" +
            "app.name=feipi-session-browser\n" +
            "app.git.commit=$gitCommitValue\n" +
            "app.build.timestamp=$buildTimestampValue\n",
            Charsets.UTF_8,
        )
    }
}

sourceSets.main.configure {
    resources.srcDir(generateBuildInfo)
}

tasks.named("processResources") {
    dependsOn(generateBuildInfo)
}

// ============================================================
// CLI 发行目录 Smoke 测试（路径含空格 + 任意 cwd）
// ============================================================
abstract class CliSmokeTestTask : DefaultTask() {

    @get:InputDirectory
    abstract val installDirectory: DirectoryProperty

    @get:Internal
    abstract val spaceDirectory: DirectoryProperty

    @TaskAction
    fun smokeTest() {
        val spaceDir = spaceDirectory.get().asFile
        if (spaceDir.exists()) spaceDir.deleteRecursively()
        spaceDir.mkdirs()
        installDirectory.get().asFile.copyRecursively(spaceDir, overwrite = true)

        val binScript = spaceDir.resolve("bin/app-cli")
        binScript.setExecutable(true)

        val workDir = temporaryDir.apply { mkdirs() }

        // 从任意 cwd 运行 --help
        val helpResult = execCli(workDir, binScript.absolutePath, "--help")
        require(helpResult.second == 0) {
            "Smoke test failed: --help exit=${helpResult.second}, stdout=${helpResult.first}"
        }
        require(helpResult.first.contains("session-browser")) {
            "Smoke test failed: --help output missing 'session-browser'"
        }
        // 验证公开子命令全部出现在 help 输出中
        val publicCommands = listOf("scan", "serve", "stop", "test", "deps", "quality", "version", "release")
        for (cmd in publicCommands) {
            require(helpResult.first.contains(cmd)) {
                "Smoke test failed: --help output missing public command '$cmd'"
            }
        }
        // 隐藏命令 normalized-batch 不应出现在 help 输出中
        require(!helpResult.first.contains("normalized-batch")) {
            "Smoke test failed: --help output contains hidden command 'normalized-batch'"
        }

        // 从任意 cwd 运行 --version
        val versionResult = execCli(workDir, binScript.absolutePath, "--version")
        require(versionResult.second == 0) {
            "Smoke test failed: --version exit=${versionResult.second}"
        }
        require(versionResult.first.contains("feipi-session-browser")) {
            "Smoke test failed: --version output missing app name"
        }
    }

    private fun execCli(workDir: File, script: String, vararg args: String): Pair<String, Int> {
        val allArgs = listOf(script, *args)
        val process = ProcessBuilder(allArgs)
            .directory(workDir)
            .redirectErrorStream(false)
            .start()
        val stdout = process.inputStream.bufferedReader().readText()
        process.errorStream.bufferedReader().readText()
        val exitCode = process.waitFor()
        return stdout to exitCode
    }
}

val cliSmokeTest = tasks.register<CliSmokeTestTask>("cliSmokeTest") {
    dependsOn(tasks.named("installDist"))
    installDirectory.set(layout.buildDirectory.dir("install/app-cli"))
    spaceDirectory.set(layout.buildDirectory.dir("path with spaces"))
}

tasks.named("check") {
    dependsOn(cliSmokeTest)
}
