pluginManagement {
    repositories {
        maven("https://maven.aliyun.com/repository/central")
        maven("https://maven.aliyun.com/repository/gradle-plugin")
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "feipi-session-browser"

includeBuild("build-logic")

include(
    "java:app-cli",
    "java:core-domain",
    "java:source-spi",
    "java:test-support",
    "java:architecture-tests",
    "java:contract-tests",
)
