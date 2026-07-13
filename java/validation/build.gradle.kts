plugins {
    id("feipi.java-library")
    id("feipi.java-test")
}

dependencies {
    api(libs.jakarta.validation.api)
    implementation(libs.hibernate.validator)
    runtimeOnly(libs.expressly)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}
