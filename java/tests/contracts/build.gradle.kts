plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(project(":java:source-spi"))
    testImplementation(project(":java:sources"))
    testImplementation(project(":java:normalization-engine"))
    testImplementation(project(":java:index-store-sqlite"))
    testImplementation(project(":java:application"))
    testImplementation(project(":java:scan-engine"))
    testImplementation(project(":java:web"))
    testImplementation(project(":java:app-cli"))
    testImplementation(project(":java:tests:support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.jackson.databind)
    testImplementation(libs.sqlite.jdbc)
    testImplementation(libs.javalin.testtools)
}

val repoRoot = rootProject.extra["repoRoot"] as org.gradle.api.file.Directory

tasks.withType<Test>().configureEach {
    systemProperty("repo.root.dir", repoRoot.asFile.absolutePath)
}

// 默认 test task 排除 sample-integration 标签的测试，
// 这些测试由独立的 sampleIntegrationTest task 执行。
tasks.named<Test>("test") {
    // 两个模块都会频繁启停本地 Javalin server，串行可避免并行端口生命周期互相干扰。
    mustRunAfter(":java:web:test")
    useJUnitPlatform {
        excludeTags("sample-integration")
    }
}

val sampleIntegrationTest = tasks.register<Test>("sampleIntegrationTest") {
    description = "运行最小脱敏 synthetic session 样例集成测试"
    group = "verification"

    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath

    useJUnitPlatform {
        includeTags("sample-integration")
    }
    filter {
        includeTestsMatching("*SessionSampleIntegrationTest*")
    }

    // 测试会从模块目录向上寻找仓库内的 synthetic fixture，无需绑定具体机器路径。
    System.getProperty("session.samples.writeExpected")?.let {
        systemProperty("session.samples.writeExpected", it)
    }

    // 样例漂移属于 required contract failure，禁止忽略失败。
    ignoreFailures = false
}
