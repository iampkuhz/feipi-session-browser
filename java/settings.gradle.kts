pluginManagement {
    repositories {
        maven("https://maven.aliyun.com/repository/central")
        maven("https://maven.aliyun.com/repository/gradle-plugin")
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "feipi-session-browser"
rootProject.projectDir = settingsDir

includeBuild("gradle/build-logic")

// 保留逻辑项目 ID；聚合项目不能与构建根或实体模块共用目录。
mapOf(
    "java" to "gradle/aggregates/java",
    "java:tests" to "gradle/aggregates/tests",
    "java:common" to "common",
    "java:app-cli" to "app-cli",
    "java:validation" to "validation",
    "java:core-domain" to "core-domain",
    "java:source-spi" to "source-spi",
    "java:sources" to "sources",
    "java:normalization-engine" to "normalization-engine",
    "java:index-api" to "index-api",
    "java:index-store-sqlite" to "index-store-sqlite",
    "java:scan-engine" to "scan-engine",
    "java:tests:support" to "tests/support",
    "java:tests:architecture" to "tests/architecture",
    "java:tests:contracts" to "tests/contracts",
    "java:tests:quality-gates" to "tests/quality-gates",
    "java:application" to "application",
    "java:web" to "web",
).forEach { (projectPath, directory) ->
    include(projectPath)
    project(":$projectPath").projectDir = file(directory)
}
