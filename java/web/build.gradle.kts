plugins {
    id("feipi.java-library")
}

dependencies {
    implementation(project(":java:validation"))
    implementation(project(":java:common"))
    implementation(project(":java:application"))
    implementation(project(":java:core-domain"))
    implementation(libs.slf4j.api)
    implementation(libs.bundles.web)
    implementation(libs.bundles.jackson)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testImplementation(libs.jackson.databind)
    testImplementation(libs.javalin.testtools)
    testImplementation(libs.sqlite.jdbc)
    testImplementation(project(":java:tests:support"))
    testImplementation(project(path = ":java:index-store-sqlite"))
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
