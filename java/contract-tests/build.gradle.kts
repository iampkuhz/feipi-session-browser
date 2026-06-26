plugins {
    id("feipi.java-test")
}

import org.gradle.api.plugins.quality.Pmd

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(project(":java:source-spi"))
    testImplementation(project(":java:source-json"))
    testImplementation(project(":java:source-claude"))
    testImplementation(project(":java:source-codex"))
    testImplementation(project(":java:artifact-normalized"))
    testImplementation(project(":java:normalization-engine"))
    testImplementation(project(":java:index-sqlite"))
    testImplementation(project(":java:query-api"))
    testImplementation(project(":java:application"))
    testImplementation(project(":java:scan-engine"))
    testImplementation(project(":java:web"))
    testImplementation(project(":java:app-cli"))
    testImplementation(project(":java:test-support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.jackson.databind)
    testImplementation(libs.sqlite.jdbc)
    testImplementation(libs.javalin.testtools)
}

// PMD 7.9.0 StackOverflow 在分析 Jackson 类型时触发，contract-tests 为纯测试模块，
// Checkstyle + Spotless 已覆盖格式和基础质量。
tasks.withType<Pmd>().configureEach {
    enabled = false
}

// 默认 test task 排除 sample-integration 标签的测试，
// 这些测试由独立的 sampleIntegrationTest task 执行。
tasks.named<Test>("test") {
    useJUnitPlatform {
        excludeTags("sample-integration")
    }
}

val sampleIntegrationTest = tasks.register<Test>("sampleIntegrationTest") {
    description = "对照 docs/session-samples/ 运行会话样例集成测试"
    group = "verification"

    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath

    useJUnitPlatform {
        includeTags("sample-integration")
    }
    filter {
        includeTestsMatching("*SessionSampleIntegrationTest*")
    }

    // 漂移报告写入项目根目录
    systemProperty("user.dir", project.rootDir.absolutePath)

    // schema 对齐完成前允许测试失败，仅生成漂移报告
    ignoreFailures = true
}
