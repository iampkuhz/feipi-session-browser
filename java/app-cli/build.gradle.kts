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
    implementation(project(":java:scan-engine"))
    implementation(project(":java:index-sqlite"))
    implementation(project(":java:application"))
    implementation(project(":java:web"))
    implementation(libs.picocli)
    implementation(libs.bundles.jackson)
    implementation(libs.sqlite.jdbc)
    implementation(libs.slf4j.api)

    testImplementation(project(":java:test-support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.javalin.testtools)
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

// ============================================================
// Distribution 可重现配置
// application 插件已自动提供 installDist / distZip / distTar。
// 此处配置可重现归档和 VERSION 文件打包。
// ============================================================
tasks.withType<Tar>().configureEach {
    compression = Compression.GZIP
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.withType<Zip>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

distributions {
    main {
        distributionBaseName.set(project.name)
        contents {
            // VERSION 文件打包到发行根目录，供 launcher 读取版本信息。
            from(rootProject.file("VERSION")) {
                into("")
            }
        }
    }
}

// ============================================================
// jdeps 模块依赖分析 —— 确定应用需要的最小 JDK 模块集合
// ============================================================
val jdepsModuleList = tasks.register("jdepsModuleList") {
    group = "distribution"
    description = "使用 jdeps 分析运行时 classpath JAR 所需的 JDK 模块清单。"

    dependsOn(tasks.named("installDist"))

    // 预解析 installDist 输出路径为字符串，避免在 doLast 中捕获 Task 引用。
    val installDistLibPath = layout.buildDirectory.dir("install/app-cli/lib")
        .get().asFile.absolutePath
    val outputDir = layout.buildDirectory.dir("reports/jdeps")
    val outputFile = outputDir.map { it.file("module-deps.txt") }

    inputs.dir(layout.buildDirectory.dir("install/app-cli/lib"))
        .withPropertyName("distLibDir")
    outputs.file(outputFile).withPropertyName("moduleDepsFile")

    doLast {
        val distLibDir = File(installDistLibPath)
        val allJars = distLibDir.listFiles()?.filter { it.name.endsWith(".jar") } ?: emptyList()

        if (allJars.isEmpty()) {
            throw org.gradle.api.GradleException("jdepsModuleList: dist lib 目录为空，请先运行 installDist")
        }

        val jdepsCmd = listOf("jdeps", "--multi-release", "base", "--print-module-deps",
            "--ignore-missing-deps") + allJars.map { it.absolutePath }

        val process = ProcessBuilder(jdepsCmd)
            .redirectErrorStream(false)
            .start()
        val stdout = process.inputStream.bufferedReader().readText().trim()
        val stderr = process.errorStream.bufferedReader().readText()
        val exitCode = process.waitFor()

        if (exitCode != 0) {
            logger.warn("jdeps 返回非零退出码 $exitCode: $stderr")
        }

        // jdeps 输出为逗号分隔的模块列表，过滤掉非模块名称的干扰行。
        val modules = stdout.lines()
            .flatMap { line -> line.split(",").map { it.trim() } }
            .filter { it.matches(Regex("[a-zA-Z][a-zA-Z0-9.]*")) && !it.contains("->") }
            .map { if (it.startsWith("java.") || it.startsWith("jdk.")) it else "java.$it" }
            .distinct()
            .sorted()

        // 基础模块始终包含，确保 logging、SQL、桌面等能力。
        val baseModules = listOf(
            "java.base", "java.logging", "java.sql", "java.desktop",
            "java.management", "java.naming",
        )
        val allModules = (modules + baseModules).distinct().sorted()

        val out = outputFile.get().asFile
        out.parentFile.mkdirs()
        out.writeText(allModules.joinToString("\n") + "\n", Charsets.UTF_8)
        logger.lifecycle("jdepsModuleList: 检测到 ${allModules.size} 个 JDK 模块: ${allModules.joinToString(", ")}")
    }
}

// ============================================================
// jlink 最小 runtime image —— 无系统 JDK 即可运行
// ============================================================
val jlinkImage = tasks.register("jlinkImage") {
    group = "distribution"
    description = "使用 jlink 创建包含最小必要 JDK 模块的自包含 runtime image。"

    dependsOn(jdepsModuleList, tasks.named("installDist"))

    val imageDir = layout.buildDirectory.dir("jlink-image")
    val moduleDepsFile = layout.buildDirectory.file("reports/jdeps/module-deps.txt")

    inputs.file(moduleDepsFile).withPropertyName("moduleDeps")
    outputs.dir(imageDir).withPropertyName("imageDir")

    doLast {
        val modules = moduleDepsFile.get().asFile.readLines()
            .filter { it.isNotBlank() }
            .map { it.trim() }

        if (modules.isEmpty()) {
            throw org.gradle.api.GradleException("jlinkImage: 模块清单为空")
        }

        val outDir = imageDir.get().asFile
        if (outDir.exists()) {
            outDir.deleteRecursively()
        }

        val javaHome = System.getenv("JAVA_HOME") ?: System.getProperty("java.home")
        val jlinkBin = File(javaHome, "bin/jlink")

        val jlinkArgs = listOf(
            jlinkBin.absolutePath,
            "--add-modules", modules.joinToString(","),
            "--no-header-files",
            "--no-man-pages",
            "--strip-debug",
            "--output", outDir.absolutePath,
        )

        val process = ProcessBuilder(jlinkArgs)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().readText()
        val exitCode = process.waitFor()

        if (exitCode != 0) {
            throw org.gradle.api.GradleException("jlink 失败 (exit=$exitCode): $output")
        }

        val sizeMb = outDir.walkTopDown()
            .filter { it.isFile }.map { it.length() }.sum() / (1024 * 1024)
        logger.lifecycle("jlinkImage: runtime image 已生成 (${sizeMb}MB), 模块: ${modules.joinToString(", ")}")
    }
}

// ============================================================
// Runtime distribution —— 包含自包含 runtime 的发行包
// ============================================================
val runtimeDistBase = layout.buildDirectory.dir("distributions/runtime-base")

val prepareRuntimeDist = tasks.register<Sync>("prepareRuntimeDist") {
    group = "distribution"
    description = "准备包含自包含 runtime 的发行目录。"

    dependsOn(jlinkImage, tasks.named("installDist"))

    // 使用预解析路径，避免 configuration cache 序列化 Task 引用。
    val installDistDirPath = layout.buildDirectory.dir("install/app-cli").get().asFile.absolutePath

    from(installDistDirPath) { into("app") }
    from(jlinkImage) { into("runtime") }
    from(rootProject.file("VERSION")) { into("") }

    into(runtimeDistBase.map { it.dir(project.name) })
}

// runtime launcher 脚本生成
val generateRuntimeLauncher = tasks.register("generateRuntimeLauncher") {
    group = "distribution"
    description = "为 runtime distribution 生成跨平台 launcher 脚本。"

    dependsOn(prepareRuntimeDist)

    val distRoot = runtimeDistBase.map { it.dir(project.name) }
    val mainClassName = application.mainClass.get()

    outputs.dir(distRoot)

    doLast {
        val root = distRoot.get().asFile
        val binDir = root.resolve("bin")
        binDir.mkdirs()

        // Unix launcher —— 使用自包含 runtime java，无需系统 JDK。
        val unixScript = binDir.resolve("run")
        unixScript.writeText(
            "#!/bin/sh\n" +
            "# Feipi Session Browser runtime launcher —— 使用自包含 runtime，无需系统 JDK。\n" +
            "SCRIPT_DIR=\"\$(cd \"\$(dirname \"\$0\")\" && pwd)\"\n" +
            "DIST_ROOT=\"\$(dirname \"\$SCRIPT_DIR\")\"\n" +
            "RUNTIME_JAVA=\"\$DIST_ROOT/runtime/bin/java\"\n" +
            "APP_HOME=\"\$DIST_ROOT/app\"\n\n" +
            "if [ ! -x \"\$RUNTIME_JAVA\" ]; then\n" +
            "    echo \"错误: runtime image 未找到，请确认发行包完整。\" >&2\n" +
            "    exit 1\n" +
            "fi\n\n" +
            "CLASSPATH=\"\"\n" +
            "for jar in \"\$APP_HOME\"/lib/*.jar; do\n" +
            "    if [ -z \"\$CLASSPATH\" ]; then\n" +
            "        CLASSPATH=\"\$jar\"\n" +
            "    else\n" +
            "        CLASSPATH=\"\$CLASSPATH:\$jar\"\n" +
            "    fi\n" +
            "done\n\n" +
            "exec \"\$RUNTIME_JAVA\" -cp \"\$CLASSPATH\" $mainClassName \"\$@\"\n",
            Charsets.UTF_8,
        )
        unixScript.setExecutable(true)

        // Windows launcher 脚本
        val winScript = binDir.resolve("run.bat")
        winScript.writeText(
            "@echo off\r\n" +
            "rem Feipi Session Browser runtime launcher —— 使用自包含 runtime，无需系统 JDK。\r\n" +
            "set SCRIPT_DIR=%~dp0\r\n" +
            "set DIST_ROOT=%SCRIPT_DIR%..\r\n" +
            "set RUNTIME_JAVA=%DIST_ROOT%\\runtime\\bin\\java.exe\r\n" +
            "set APP_HOME=%DIST_ROOT%\\app\r\n\r\n" +
            "if not exist \"%RUNTIME_JAVA%\" (\r\n" +
            "    echo 错误: runtime image 未找到，请确认发行包完整。\r\n" +
            "    exit /b 1\r\n" +
            ")\r\n\r\n" +
            "set CLASSPATH=\r\n" +
            "for %%j in (\"%APP_HOME%\\lib\\*.jar\") do call :addcp \"%%j\"\r\n" +
            "goto :run\r\n\r\n" +
            ":addcp\r\n" +
            "if \"%CLASSPATH%\"==\"\" (set CLASSPATH=%~1) else (set CLASSPATH=%CLASSPATH%;%~1)\r\n" +
            "goto :eof\r\n\r\n" +
            ":run\r\n" +
            "\"%RUNTIME_JAVA%\" -cp \"%CLASSPATH%\" $mainClassName %*\r\n",
            Charsets.UTF_8,
        )

        logger.lifecycle("generateRuntimeLauncher: launcher 脚本已生成于 ${binDir.absolutePath}")
    }
}

tasks.register<Zip>("runtimeDistZip") {
    group = "distribution"
    description = "打包包含自包含 runtime 的 ZIP 发行包。"

    dependsOn(generateRuntimeLauncher)

    archiveBaseName.set("${project.name}-runtime")
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true

    from(runtimeDistBase)
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}

tasks.register<Tar>("runtimeDistTar") {
    group = "distribution"
    description = "打包包含自包含 runtime 的 tar.gz 发行包。"

    dependsOn(generateRuntimeLauncher)

    archiveBaseName.set("${project.name}-runtime")
    compression = Compression.GZIP
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true

    from(runtimeDistBase)
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}
