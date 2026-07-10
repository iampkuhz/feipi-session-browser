import org.gradle.api.artifacts.VersionCatalogsExtension

plugins {
    `java`
}

val catalog = project.extensions.getByType<VersionCatalogsExtension>().named("libs")
val lombokVersion = catalog.findVersion("lombok").get().requiredVersion
val hibernateValidatorVersion = catalog.findVersion("hibernate-validator").get().requiredVersion

// --- Java 版本通过 running JVM 提供（CI 使用 setup-java，本地使用 SDKMAN/JAVA_HOME）---
// release(25) 确保编译目标为 Java 25。

// --- 编译器编码与告警 ---
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(25)
    options.compilerArgs.addAll(
        listOf(
            "-Xlint:all",
            // Lombok 注解处理器仅消费 Lombok 注解；
            // @DomainModel、@CoreField 等仓库注解无需处理器认领。
            "-Xlint:-processing",
            "-Werror",
        ),
    )
}

// --- 公共仓库 ---
repositories {
    maven("https://maven.aliyun.com/repository/central")
    mavenCentral()
}

// --- Lombok 与 Hibernate Validator 注解处理器依赖 ---
dependencies {
    "compileOnly"("org.projectlombok:lombok:$lombokVersion")
    "annotationProcessor"("org.projectlombok:lombok:$lombokVersion")
    "annotationProcessor"(
        "org.hibernate.validator:hibernate-validator-annotation-processor:$hibernateValidatorVersion"
    )
    "testAnnotationProcessor"(
        "org.hibernate.validator:hibernate-validator-annotation-processor:$hibernateValidatorVersion"
    )
}

// --- 可复现构建默认值 ---
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
