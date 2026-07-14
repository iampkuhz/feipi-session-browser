plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}

tasks.withType<Test>().configureEach {
    jvmArgs("--add-modules", "jdk.compiler")
}

val javaQualityRules = providers.gradleProperty("feipiJavaQualityRules")
    .orElse("record-component-javadocs,no-pmd-suppressions")
val changedFiles = providers.environmentVariable("QUALITY_CHANGED_FILES").orElse("")
val writeApiSnapshot = providers.gradleProperty("feipiJavaApiSnapshotWrite")
    .map(String::toBoolean)
    .orElse(false)
val apiSnapshot = rootProject.layout.projectDirectory.file("config/api-snapshots/java-public-api.txt")
val summary = layout.buildDirectory.file("reports/java-quality-gates/summary.json")
val javaMainSources = rootProject.fileTree("java") {
    include("**/src/main/java/**/*.java")
    exclude("**/build/**")
}

// 所有 Java source rules 共用这一项公开 JavaExec；禁止增加逐 rule alias/task。
tasks.register<JavaExec>("runJavaQualityGates") {
    group = "verification"
    description = "在单 JVM 内运行选中的 Java source quality rules。"
    mainClass.set("com.feipi.session.browser.quality.gates.cli.QualityGateCli")
    classpath = sourceSets["main"].runtimeClasspath
    jvmArgs("--add-modules", "jdk.compiler")

    inputs.files(javaMainSources).withPropertyName("javaMainSources").withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.property("rules", javaQualityRules)
    inputs.property("changedFiles", changedFiles)
    inputs.property("writeApiSnapshot", writeApiSnapshot)
    outputs.file(summary).withPropertyName("summary")
    if (writeApiSnapshot.get()) {
        outputs.file(apiSnapshot).withPropertyName("apiSnapshot")
    } else {
        inputs.file(apiSnapshot).withPropertyName("apiSnapshot").withPathSensitivity(PathSensitivity.RELATIVE)
    }
    outputs.cacheIf("deterministic compiler AST report") { true }

    args(
        "--repo-root", rootProject.projectDir.absolutePath,
        "--paths", rootProject.file("java").absolutePath,
        "--rules", javaQualityRules.get(),
        "--api-snapshot", apiSnapshot.asFile.absolutePath,
        "--report-file", summary.get().asFile.absolutePath,
    )
    if (changedFiles.get().isNotBlank()) {
        args("--changed-files", changedFiles.get())
    }
    if (writeApiSnapshot.get()) {
        args("--write-api-snapshot")
    }
}
