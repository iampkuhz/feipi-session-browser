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

// ============================================================
// verifyJavaRecordComponentJavadocs —— Java 质量门 CLI 执行。
// ============================================================
val verifyJavaRecordComponentJavadocs = tasks.register<JavaExec>("verifyJavaRecordComponentJavadocs") {
    group = "verification"
    description = "Java 实现的 record component Javadoc 门禁。"

    mainClass.set("com.feipi.session.browser.quality.gates.cli.QualityGateCli")
    classpath = sourceSets["main"].runtimeClasspath

    val reportFile = layout.buildDirectory.file("reports/java-record-component-javadocs/result.txt")
    args(
        "--gate", "record-component-javadocs",
        "--repo-root", rootProject.projectDir.absolutePath,
        "--paths", rootProject.file("java").absolutePath,
        "--report-file", reportFile.get().asFile.absolutePath,
    )

    inputs.files(
        rootProject.fileTree("java").apply {
            include("**/src/main/java/**/*.java")
            exclude("**/build/**")
        },
    ).withPropertyName("javaMainSourceFiles")
    outputs.file(reportFile).withPropertyName("resultFile")
}

// ============================================================
// verifyJavaQualityGates —— 聚合所有 Java 质量门。
// ============================================================
val verifyJavaQualityGates = tasks.register("verifyJavaQualityGates") {
    group = "verification"
    description = "聚合所有 Java 质量门执行。"
    dependsOn(verifyJavaRecordComponentJavadocs)
}
