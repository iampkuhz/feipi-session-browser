pluginManagement {
    repositories {
        maven("https://maven.aliyun.com/repository/central")
        maven("https://maven.aliyun.com/repository/gradle-plugin")
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "feipi-session-browser"

include(
    "java:app-cli",
    "java:core-domain",
    "java:test-support",
    "java:architecture-tests"
)
