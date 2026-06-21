plugins {
    `java`
}

// --- Java toolchain ---
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

// --- Compiler encoding and warnings ---
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

// --- Common repositories ---
repositories {
    maven("https://maven.aliyun.com/repository/central")
    mavenCentral()
}

// --- Reproducible build defaults ---
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
