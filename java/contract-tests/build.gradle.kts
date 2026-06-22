plugins {
    id("feipi.java-test")
}

import org.gradle.api.plugins.quality.Pmd

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(project(":java:source-spi"))
    testImplementation(project(":java:test-support"))
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.jackson.databind)
}

// PMD 7.9.0 StackOverflow 在分析 Jackson 类型时触发，contract-tests 为纯测试模块，
// Checkstyle + Spotless 已覆盖格式和基础质量。
tasks.withType<Pmd>().configureEach {
    enabled = false
}
