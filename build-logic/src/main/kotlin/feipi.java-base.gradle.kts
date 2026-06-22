plugins {
    `java`
}

// --- Java 工具链 ---
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

// --- 编译器编码与告警 ---
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(25)
    options.compilerArgs.addAll(
        listOf(
            "-Xlint:all",
            "-Werror",
        ),
    )
}

// --- 公共仓库 ---
repositories {
    maven("https://maven.aliyun.com/repository/central")
    mavenCentral()
}

// --- 可复现构建默认值 ---
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
