plugins {
    alias(libs.plugins.spotless) apply false
    alias(libs.plugins.spotbugs) apply false
    alias(libs.plugins.forbiddenapis) apply false
    alias(libs.plugins.pitest) apply false
    alias(libs.plugins.cyclonedx) apply false
}

group = "com.feipi.session.browser"
version = file("VERSION").readText().trim()

subprojects {
    group = rootProject.group
    version = rootProject.version

    repositories {
        maven("https://maven.aliyun.com/repository/central")
        mavenCentral()
    }
}

dependencyLocking {
    lockAllConfigurations()
}
