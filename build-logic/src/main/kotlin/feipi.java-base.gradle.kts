plugins {
    `java`
}

// --- Java 版本通过 running JVM 提供（CI 使用 setup-java，本地使用 SDKMAN/JAVA_HOME）---
// release(25) 确保编译目标为 Java 25。

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
