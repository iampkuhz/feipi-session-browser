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
    "app-cli",
    "java:app-cli",
    "java:core-domain",
    "java:source-spi",
    "java:sources",
    "java:artifact-normalized",
    "java:normalization-engine",
    "java:index-sqlite",
    "java:scan-engine",
    "java:tests:support",
    "java:tests:architecture",
    "java:tests:contracts",
    "java:application",
    "java:web",
)
