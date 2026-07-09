plugins {
    id("feipi.java-library")
}

dependencies {
    api(project(":java:source-spi"))
    api(project(":java:index-api"))
    api(project(":java:index-store-sqlite"))
    api(libs.junit.jupiter)
    api(libs.assertj.core)
    implementation(libs.sqlite.jdbc)
}
