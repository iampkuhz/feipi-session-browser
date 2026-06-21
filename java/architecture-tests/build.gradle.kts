plugins {
    `java-library`
}

java {
    toolchain {
        // Production target is Java 25; using Java 21 LTS toolchain until Java 25 is available.
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(libs.archunit.junit5)
    testImplementation(libs.junit.jupiter)
}
