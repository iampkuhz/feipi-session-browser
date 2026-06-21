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
    api(libs.junit.jupiter)
    api(libs.assertj.core)
}
