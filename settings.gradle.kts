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
    "java:source-json",
    "java:artifact-normalized",
    "java:source-claude",
    "java:source-codex",
    "java:source-qoder",
    "java:normalization-engine",
    "java:index-sqlite",
    "java:scan-engine",
    "java:test-support",
    "java:architecture-tests",
    "java:contract-tests",
    "java:query-api",
    "java:reuse-analyzer",
    "java:application",
)
