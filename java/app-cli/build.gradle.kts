plugins {
    application
}

application {
    mainClass.set("com.feipi.session.browser.cli.App")
}

java {
    toolchain {
        // Production target is Java 25; using Java 21 LTS toolchain until Java 25 is available.
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    implementation(project(":java:core-domain"))
}
