import java.time.Instant
import java.util.zip.ZipFile
import org.gradle.jvm.application.scripts.TemplateBasedScriptGenerator
import org.gradle.jvm.application.tasks.CreateStartScripts

plugins {
    id("feipi.java-application")
    id("feipi.java-test")
}

val repoRoot = rootProject.extra["repoRoot"] as org.gradle.api.file.Directory
val sourceVersionFile = rootProject.layout.projectDirectory.file("gradle/VERSION")
// 发行工具跟随实际 Gradle JVM，不再各自从 PATH/JAVA_HOME 选择另一套 JDK。
val distributionJdk = File(System.getProperty("java.home"))
val jdkExecutableSuffix = if (System.getProperty("os.name").startsWith("Windows")) ".exe" else ""
val runtimeLayout = layout.buildDirectory.dir("runtime-layout")

// 产品 launcher 是 JVM profile 的唯一 owner；full scan 需要更大的有界堆。
val standardLauncherJvmArgs = listOf(
    "-XX:+UseSerialGC",
    "-Xms16m",
    "-Xmx128m",
    "--enable-native-access=ALL-UNNAMED",
)
val fullScanLauncherJvmArgs = standardLauncherJvmArgs.map {
    if (it == "-Xmx128m") "-Xmx512m" else it
}

application {
    mainClass.set("com.feipi.session.browser.cli.App")
    // 启动优化：Serial GC 加快冷启动，限制堆内存降低空闲 RSS
    applicationDefaultJvmArgs = standardLauncherJvmArgs
}

// Gradle 生成的 launcher 根据 Java CLI 参数选择 profile，避免在公开 shell 里复制 JVM 逻辑。
tasks.named<CreateStartScripts>("startScripts") {
    val fullScanUnix = "'" + fullScanLauncherJvmArgs.joinToString(" ") { "\"$it\"" } + "'"
    val unixMarker = "DEFAULT_JVM_OPTS=${'$'}{defaultJvmOpts}"
    val unixProfile = """
        $unixMarker

        # full scan 和 serve 的有界堆由 launcher 统一选择；用户 JAVA_OPTS/APP_CLI_OPTS 仍可覆盖。
        # serve 在后台执行 bootstrap 全量重建，需要与 scan --full 相当的堆预算。
        case "\${'$'}{1:-}" in
            scan)
                for arg in "\${'$'}@"
                do
                    if [ "\${'$'}arg" = "--full" ]
                    then
                        DEFAULT_JVM_OPTS=$fullScanUnix
                        break
                    fi
                done
                ;;
            serve)
                DEFAULT_JVM_OPTS=$fullScanUnix
                ;;
        esac
    """.trimIndent()
    val unixGenerator = unixStartScriptGenerator as TemplateBasedScriptGenerator
    val unixTemplate = unixGenerator.template.asString()
    require(unixTemplate.contains(unixMarker)) { "startScripts 缺少预期的 Unix JVM profile 模板" }
    unixGenerator.template = resources.text.fromString(unixTemplate.replace(unixMarker, unixProfile))

    val fullScanWindows = fullScanLauncherJvmArgs.joinToString(" ") { "\"$it\"" }
    val windowsMarker = "set DEFAULT_JVM_OPTS=${'$'}{defaultJvmOpts}"
    val windowsProfile = """
        $windowsMarker
        @rem full scan 和 serve 的有界堆由 launcher 统一选择。
        if "%~1"=="scan" (
            for %%a in (%*) do if "%%~a"=="--full" set DEFAULT_JVM_OPTS=$fullScanWindows
        )
        if "%~1"=="serve" set DEFAULT_JVM_OPTS=$fullScanWindows
    """.trimIndent()
    val windowsGenerator = windowsStartScriptGenerator as TemplateBasedScriptGenerator
    val windowsTemplate = windowsGenerator.template.asString()
    require(windowsTemplate.contains(windowsMarker)) {
        "startScripts 缺少预期的 Windows JVM profile 模板"
    }
    windowsGenerator.template = resources.text.fromString(
        windowsTemplate.replace(windowsMarker, windowsProfile),
    )
}

dependencies {
    implementation(project(":java:validation"))
    implementation(project(":java:core-domain"))
    implementation(project(":java:source-spi"))
    implementation(project(":java:sources"))
    implementation(project(":java:normalization-engine"))
    implementation(project(":java:scan-engine"))
    implementation(project(":java:index-api"))
    implementation(project(":java:index-store-sqlite"))
    implementation(project(":java:application"))
    implementation(project(":java:web"))
    implementation(libs.picocli)
    implementation(libs.bundles.jackson)
    implementation(libs.sqlite.jdbc)
    implementation(libs.slf4j.api)
    runtimeOnly(libs.logback.classic) {
        exclude(group = "org.slf4j", module = "slf4j-api")
    }

    testImplementation(project(":java:tests:support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.javalin.testtools)
}

tasks.named<Test>("test") {
    // 发行目录契约必须消费本轮准备完成的产物，不能依赖上次构建留下的目录。
    dependsOn(tasks.named("installDist"))
    dependsOn("prepareRuntimeDist")
    val installDir = layout.buildDirectory.dir("install/app-cli")
    inputs.dir(installDir).withPropertyName("cliInstallDistribution")
    systemProperty("cli.install.dir", installDir.get().asFile.absolutePath)
    val runtimeDir = runtimeLayout
    inputs.dir(runtimeDir).withPropertyName("cliRuntimeDistribution")
    systemProperty("cli.runtime.dir", runtimeDir.get().asFile.absolutePath)
}

// ============================================================
// build-info.properties 生成
// git commit 和 build timestamp 通过环境变量可覆盖，确保相同输入可复现。
// ============================================================
val generateBuildInfo = tasks.register("generateBuildInfo") {
    val versionFile = sourceVersionFile.asFile
    val projectDirFile = repoRoot.asFile
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

    inputs.file(versionFile)
    inputs.property("gitCommit", gitCommitProvider)
    // 只有显式时间属于输入；默认当前时间在任务执行时生成，不能让时钟使候选持续失效。
    inputs.property("buildTimestamp", buildTimestampProvider).optional(true)
    outputs.dir(outputDir)

    val gitCommitValue = gitCommitProvider.get()
    val explicitBuildTimestamp = buildTimestampProvider.orNull

    doLast {
        val buildTimestampValue = explicitBuildTimestamp ?: Instant.now().toString()
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

        val windows = System.getProperty("os.name").startsWith("Windows")
        val binScript = spaceDir.resolve(if (windows) "bin/app-cli.bat" else "bin/app-cli")
        if (!windows) binScript.setExecutable(true)

        val launcherContent = binScript.readText(Charsets.UTF_8)
        require(launcherContent.contains("-Xmx128m") && launcherContent.contains("-Xmx512m")) {
            "Smoke test failed: launcher 未同时包含标准/full-scan JVM profile"
        }

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
        val publicCommands = listOf("scan", "serve", "stop", "status", "doctor", "deps", "version", "diagnose")
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
        require(versionResult.first.trim().matches(Regex("""\d+\.\d+(\.\d+)?(-[\w.]+)?"""))) {
            "Smoke test failed: --version output is not a plain version"
        }
    }

    private fun execCli(workDir: File, script: String, vararg args: String): Pair<String, Int> {
        val allArgs = if (System.getProperty("os.name").startsWith("Windows")) {
            listOf("cmd.exe", "/d", "/c", script, *args)
        } else {
            listOf(script, *args)
        }
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
}

distributions {
    main {
        distributionBaseName.set(project.name)
        contents {
            // VERSION 文件打包到发行根目录，供 launcher 读取版本信息。
            from(sourceVersionFile) {
                into("")
            }
        }
    }
}

// generic 保留原始全平台 JDBC；只有宿主 runtime 包使用裁剪后的同名 JAR。
// Linux 同时保留 glibc/musl，不能以构建机 libc 推断使用者的环境。
fun sqliteNativePaths(os: String, arch: String): List<String> = when (os) {
    "Mac OS X" -> when (arch) {
        "aarch64", "arm64" -> listOf("Mac/aarch64")
        "x86_64", "amd64" -> listOf("Mac/x86_64")
        else -> emptyList()
    }
    "Linux" -> when (arch) {
        "x86_64", "amd64" -> listOf("Linux/x86_64", "Linux-Musl/x86_64")
        else -> emptyList()
    }
    else -> if (os.startsWith("Windows") &&
        arch in listOf("amd64", "x86_64")) {
        listOf("Windows/x86_64")
    } else {
        // 未声明的宿主不猜测 SQLite 的平台映射，安全保留全部 native。
        emptyList()
    }
}
val nativeSqlitePaths = sqliteNativePaths(System.getProperty("os.name"), System.getProperty("os.arch"))
val sqliteJdbcJar = configurations.runtimeClasspath.map { classpath ->
    classpath.single { it.name.startsWith("sqlite-jdbc-") && it.extension == "jar" }
}
val nativeSqliteJar = tasks.register<Zip>("nativeSqliteJar") {
    group = "distribution"
    description = "仅为宿主 runtime 发行包保留目标 SQLite native，保留类、SPI、许可与来源。"
    archiveFileName.set(sqliteJdbcJar.map { it.name })
    destinationDirectory.set(layout.buildDirectory.dir("native-libs"))
    inputs.property("nativePaths", nativeSqlitePaths)
    val requiredPaths = nativeSqlitePaths
    from(zipTree(sqliteJdbcJar)) {
        exclude { entry ->
            entry.path.startsWith("org/sqlite/native/") && requiredPaths.isNotEmpty() &&
                requiredPaths.none { entry.path.startsWith("org/sqlite/native/$it/") }
        }
    }
    includeEmptyDirs = false
    val sourceJar = sqliteJdbcJar
    doFirst {
        ZipFile(sourceJar.get()).use { jar ->
            val names = jar.entries().asSequence().filter { !it.isDirectory }.map { it.name }.toList()
            require(names.none { it.matches(Regex("META-INF/[^/]+\\.(SF|RSA|DSA|EC)", RegexOption.IGNORE_CASE)) }) {
                "不能裁剪已签名的 SQLite JAR"
            }
            requiredPaths.forEach { path ->
                require(names.any { it.startsWith("org/sqlite/native/$path/") }) {
                    "SQLite JAR 缺少目标 native: $path"
                }
            }
        }
    }
}
val runtimeJars = files(tasks.named("jar"), configurations.runtimeClasspath)

// ============================================================
// jdeps 模块依赖分析 —— 确定应用需要的最小 JDK 模块集合
// ============================================================
val jdepsModuleList = tasks.register("jdepsModuleList") {
    group = "distribution"
    description = "使用 jdeps 分析运行时 classpath JAR 所需的 JDK 模块清单。"

    dependsOn(tasks.named("jar"))

    // 直接分析原始 JAR，不为 jdeps 复制完整 installDist。
    val jars = runtimeJars
    val outputDir = layout.buildDirectory.dir("reports/jdeps")
    val outputFile = outputDir.map { it.file("module-deps.txt") }
    val jdepsExecutable = distributionJdk.resolve("bin/jdeps$jdkExecutableSuffix")

    inputs.property("jdkHome", distributionJdk.absolutePath)
    inputs.file(distributionJdk.resolve("release")).withPropertyName("jdkRelease")
    inputs.file(jdepsExecutable).withPropertyName("jdepsExecutable")
    inputs.files(jars).withPropertyName("runtimeJars")
    outputs.file(outputFile).withPropertyName("moduleDepsFile")

    doLast {
        val allJars = jars.files.filter { it.name.endsWith(".jar") }

        if (allJars.isEmpty()) {
            throw org.gradle.api.GradleException("jdepsModuleList: runtime classpath 为空")
        }

        val jdepsCmd = listOf(jdepsExecutable.absolutePath, "--multi-release", "base", "--print-module-deps",
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

        // 基础模块：仅包含运行时真实依赖的 JDK 模块。
        // java.desktop/java.management 不属于当前运行时必需路径：
        //   - java.desktop：仅 jackson-databind 可选 AWT 引用，运行时通过反射守卫跳过
        //   - java.management：本应用不使用 Jetty JMX
        // java.naming：Jetty 正常 Web 初始化动态加载 NamingException，jdeps 静态分析无法捕获
        // jdk.zipfs：Jetty 通过 FileSystems provider 读取 JAR 内的 classpath 静态资源
        // java.net.http：StopCommand 使用 HttpClient 发送 HTTP 请求
        val baseModules = listOf(
            "java.base", "java.logging", "java.sql", "java.net.http", "java.naming", "jdk.zipfs",
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

    dependsOn(jdepsModuleList)

    val imageDir = runtimeLayout.map { it.dir("runtime") }
    val moduleDepsFile = layout.buildDirectory.file("reports/jdeps/module-deps.txt")
    val jlinkExecutable = distributionJdk.resolve("bin/jlink$jdkExecutableSuffix")

    inputs.property("jdkHome", distributionJdk.absolutePath)
    inputs.file(distributionJdk.resolve("release")).withPropertyName("jdkRelease")
    inputs.file(jlinkExecutable).withPropertyName("jlinkExecutable")
    inputs.dir(distributionJdk.resolve("jmods")).withPropertyName("jdkModules")
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

        val jlinkArgs = listOf(
            jlinkExecutable.absolutePath,
            "--add-modules", modules.joinToString(","),
            "--no-header-files",
            "--no-man-pages",
            "--strip-debug",
            // JDK 21+ 压缩格式，zip-6 提供最佳压缩比，runtime image 体积减少 30-50%
            "--compress", "zip-6",
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
// jlink、launcher 与测试应用各自拥有独立输出，测试直接使用原始 runtime。
val runtimeLauncherDirectory = runtimeLayout.map { it.dir("bin") }
val runtimeVersionFile = runtimeLayout.map { it.file("VERSION") }

val generateRuntimeLauncher = tasks.register("generateRuntimeLauncher") {
    group = "distribution"
    description = "为 runtime distribution 生成跨平台 launcher 脚本。"

    val launcherDir = runtimeLauncherDirectory
    val versionOutput = runtimeVersionFile
    val versionSource = sourceVersionFile.asFile
    val mainClassName = application.mainClass.get()
    // 配置期冻结共享 JVM 参数，执行期不再捕获 Gradle script 对象。
    val standardJvmArgs = standardLauncherJvmArgs.joinToString(" ")
    val fullScanJvmArgs = fullScanLauncherJvmArgs.joinToString(" ")

    // 内联 launcher 模板变化必须使已有发行目录失效并重新生成。
    inputs.file(layout.projectDirectory.file("build.gradle.kts"))
    inputs.file(versionSource)
    outputs.dir(launcherDir)
    outputs.file(versionOutput)

    doLast {
        val binDir = launcherDir.get().asFile
        binDir.mkdirs()
        versionSource.copyTo(versionOutput.get().asFile, overwrite = true)

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
            "JVM_ARGS=\"$standardJvmArgs\"\n" +
            "case \"\${1:-}\" in\n" +
            "    scan)\n" +
            "        for arg in \"\$@\"; do\n" +
            "            if [ \"\$arg\" = \"--full\" ]; then JVM_ARGS=\"$fullScanJvmArgs\"; break; fi\n" +
            "        done\n" +
            "        ;;\n" +
            "    serve)\n" +
            "        JVM_ARGS=\"$fullScanJvmArgs\"\n" +
            "        ;;\n" +
            "esac\n\n" +
            "exec \"\$RUNTIME_JAVA\" \$JVM_ARGS -cp \"\$CLASSPATH\" $mainClassName \"\$@\"\n",
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
            // 交给 Java 展开 JAR 通配符，避免 cmd 逐 JAR 拼接超过 8191 字符。
            "set \"CLASSPATH=%APP_HOME%\\lib\\*\"\r\n" +
            "set JVM_ARGS=$standardJvmArgs\r\n" +
            "if \"%~1\"==\"scan\" for %%a in (%*) do if \"%%~a\"==\"--full\" set JVM_ARGS=$fullScanJvmArgs\r\n" +
            "if \"%~1\"==\"serve\" set JVM_ARGS=$fullScanJvmArgs\r\n" +
            "\"%RUNTIME_JAVA%\" %JVM_ARGS% -cp \"%CLASSPATH%\" $mainClassName %*\r\n",
            Charsets.UTF_8,
        )

        logger.lifecycle("generateRuntimeLauncher: launcher 脚本已生成于 ${binDir.absolutePath}")
    }
}

// 测试只准备应用文件，直接复用 jlink image 和 launcher，不复制整个 runtime。
val runtimeAppContents = copySpec {
    from(tasks.named("startScripts")) {
        into("bin")
        filesMatching("app-cli") { permissions { unix("0755") } }
    }
    from(sourceVersionFile)
    from(runtimeJars) {
        into("lib")
        exclude("sqlite-jdbc-*.jar")
    }
    from(nativeSqliteJar) { into("lib") }
}

val prepareRuntimeDist = tasks.register<Sync>("prepareRuntimeDist") {
    group = "verification"
    description = "只为真实 runtime 测试准备应用文件，不复制 jlink image。"
    dependsOn(generateRuntimeLauncher, jlinkImage)
    with(runtimeAppContents)
    into(runtimeLayout.map { it.dir("app") })
}

val runtimeContents = copySpec {
    into("app-cli") {
        from(runtimeLauncherDirectory) {
            into("bin")
            filesMatching("run") { permissions { unix("0755") } }
        }
        from(runtimeVersionFile)
        into("app") { with(runtimeAppContents) }
        from(jlinkImage) {
            into("runtime")
            filesMatching(listOf("bin/*", "lib/jspawnhelper")) { permissions { unix("0755") } }
        }
    }
}

fun AbstractArchiveTask.configureRuntimeArchive() {
    dependsOn(generateRuntimeLauncher)
    archiveBaseName.set("${project.name}-runtime")
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    filePermissions { unix("0644") }
    dirPermissions { unix("0755") }
    with(runtimeContents)
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}
tasks.register<Zip>("runtimeDistZip") {
    group = "distribution"
    description = "直接打包包含自包含 runtime 的 ZIP 发行包。"
    configureRuntimeArchive()
}
tasks.register<Tar>("runtimeDistTar") {
    group = "distribution"
    description = "直接打包包含自包含 runtime 的 tar.gz 发行包。"
    compression = Compression.GZIP
    configureRuntimeArchive()
}
