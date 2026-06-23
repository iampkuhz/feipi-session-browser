plugins {
    id("feipi.java-library")
    id("feipi.java-test")
}

dependencies {
    // Spoon 只作为构建期工具，使用 implementation 不暴露给消费方。
    // 绝不进入产品 runtimeClasspath 或 distribution。
    implementation(libs.spoon.core)
    implementation(libs.bundles.jackson)
    implementation(libs.slf4j.api)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testRuntimeOnly(libs.logback.classic)
}
