plugins {
    id("feipi.java-library")
}

dependencies {
    api(project(":java:validation"))
    implementation(libs.sqlite.jdbc)
    implementation(libs.slf4j.api)
    implementation(libs.bundles.jackson)
    implementation(project(":java:common"))
    implementation(project(":java:core-domain"))
    api(project(":java:index-api"))

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(project(":java:tests:support"))
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
