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
    implementation(libs.picocli)

    testImplementation(project(":java:test-support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}

// ============================================================
// build-info.properties 生成
// ============================================================
val generateBuildInfo = tasks.register("generateBuildInfo") {
    val versionFile = rootProject.file("VERSION")
    val projectDirFile = rootProject.projectDir
    val outputDir = layout.buildDirectory.dir("generated/build-info")
    inputs.file(versionFile)
    outputs.dir(outputDir)

    doLast {
        val version = versionFile.readText().trim()
        val gitCommit = try {
            val proc = ProcessBuilder("git", "rev-parse", "--short=12", "HEAD")
                .directory(projectDirFile)
                .redirectErrorStream(true)
                .start()
            proc.inputStream.bufferedReader().readText().trim().also { proc.waitFor() }
        } catch (ex: Exception) {
            "unknown"
        }
        val buildTimestamp = Instant.now().toString()

        val propsDir = outputDir.get().asFile.resolve("com/feipi/session/browser/cli")
        propsDir.mkdirs()
        propsDir.resolve("build-info.properties").writeText(
            "app.version=$version\n" +
            "app.name=feipi-session-browser\n" +
            "app.git.commit=$gitCommit\n" +
            "app.build.timestamp=$buildTimestamp\n",
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
