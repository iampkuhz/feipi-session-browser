plugins {
    id("feipi.java-library")
    id("feipi.java-test")
}

dependencies {
    api(project(":java:source-spi"))
    implementation(project(":java:core-domain"))
    implementation(project(":java:normalization-engine"))
    implementation(project(":java:artifact-normalized"))
    implementation(libs.bundles.jackson)

    testImplementation(project(":java:test-support"))
}
