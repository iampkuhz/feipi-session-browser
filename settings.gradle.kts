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
    "java:common",
    "java:app-cli",
    "java:validation",
    "java:core-domain",
    "java:source-spi",
    "java:sources",
    "java:normalization-engine",
    "java:index-api",
    "java:index-store-sqlite",
    "java:scan-engine",
    "java:tests:support",
    "java:tests:architecture",
    "java:tests:contracts",
    "java:tests:quality-gates",
    "java:application",
    "java:web",
)
