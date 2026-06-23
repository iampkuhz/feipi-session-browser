plugins {
    id("feipi.java-library")
}

dependencies {
    implementation(project(":java:query-api"))
    implementation(project(":java:index-sqlite"))
    implementation(project(":java:core-domain"))
    implementation(libs.slf4j.api)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.sqlite.jdbc)
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
