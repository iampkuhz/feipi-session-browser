plugins {
    id("feipi.java-library")
    id("feipi.java-test")
}

dependencies {
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}
