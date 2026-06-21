plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(libs.archunit.junit5)
    testImplementation(libs.junit.jupiter)
}
