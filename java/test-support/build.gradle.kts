plugins {
    id("feipi.java-library")
}

dependencies {
    api(project(":java:source-spi"))
    api(libs.junit.jupiter)
    api(libs.assertj.core)
}
