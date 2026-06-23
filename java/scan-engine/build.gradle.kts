plugins {
    id("feipi.java-library")
}

dependencies {
    implementation(project(":java:core-domain"))
    implementation(project(":java:source-spi"))
    implementation(project(":java:source-json"))
    implementation(project(":java:normalization-engine"))
    implementation(project(":java:artifact-normalized"))
    implementation(project(":java:index-sqlite"))
    implementation(libs.slf4j.api)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(project(":java:test-support"))
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = false
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
