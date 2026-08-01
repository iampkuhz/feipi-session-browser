plugins {
    id("feipi.java-test")
}

dependencies {
    implementation(libs.jackson.databind)
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
val baselineUpdateRules = providers.gradleProperty("feipiJavaQualityBaselineUpdateRules").orElse("")
val apiSnapshot = rootProject.layout.projectDirectory.file("config/api-snapshots/java-public-api.txt")
val technicalTermsPolicy = rootProject.layout.projectDirectory.file("config/technical-terms.json")
val templatesRoot = rootProject.layout.projectDirectory.dir("java/web/src/main/resources/templates")
val staticRoot = rootProject.layout.projectDirectory.dir("java/web/src/main/resources/static")
val cssRoot = staticRoot.dir("css")
val webQualityBaseline = rootProject.layout.projectDirectory.file("config/web-quality-baselines.json")
val summary = layout.buildDirectory.file("reports/java-quality-gates/summary.json")
val javaMainSources = rootProject.fileTree("java") {
    include("**/src/main/java/**/*.java")
    exclude("**/build/**")
}
val jvmCommentSources = rootProject.files(
    rootProject.fileTree("java") {
        include("**/*.java", "**/*.kt", "**/*.kts")
        exclude("**/build/**", "**/.gradle/**", "**/generated/**", "**/gen/**")
    },
    rootProject.fileTree("gradle/build-logic") {
        include("**/*.java", "**/*.kt", "**/*.kts")
        exclude("**/build/**", "**/.gradle/**", "**/generated/**")
    },
    rootProject.layout.projectDirectory.file("build.gradle.kts"),
    rootProject.layout.projectDirectory.file("settings.gradle.kts"),
)
val templateSources = rootProject.fileTree(templatesRoot) {
    include("**/*.html")
}
val staticResourceSources = rootProject.fileTree(staticRoot) {
    include("**/*.css", "**/*.js")
}
val cssOwnershipSources = rootProject.fileTree(cssRoot) {
    include("*.css")
}
val staticJavaScriptSources = rootProject.fileTree(staticRoot.dir("js")) {
    include("**/*.js")
}
val testJavaScriptSources = rootProject.fileTree("tests") {
    include("**/*.js")
}
val scriptJavaScriptSources = rootProject.fileTree("scripts") {
    include("**/*.js")
}

// 所有 Java source rules 共用这一项公开 JavaExec；禁止增加逐 rule alias/task。
tasks.register<JavaExec>("runJavaQualityGates") {
    group = "verification"
    description = "在单 JVM 内运行选中的 Java source quality rules。"
    mainClass.set("com.feipi.session.browser.quality.gates.cli.QualityGateCli")
    classpath = sourceSets["main"].runtimeClasspath
    jvmArgs("--add-modules", "jdk.compiler")

    val selectedRules = javaQualityRules.get().split(',').map(String::trim)
    val javaSourceRules = setOf("record-component-javadocs", "no-pmd-suppressions", "java-api-snapshot")
    if (selectedRules.any(javaSourceRules::contains)) {
        inputs.files(javaMainSources)
            .withPropertyName("javaMainSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
    }
    if ("java-comment-language" in selectedRules) {
        inputs.files(jvmCommentSources)
            .withPropertyName("jvmCommentSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
        inputs.file(technicalTermsPolicy)
            .withPropertyName("technicalTermsPolicy")
            .withPathSensitivity(PathSensitivity.RELATIVE)
    }
    if (selectedRules.any(setOf("template-contract", "static-resource-contract", "layout-inline-style")::contains)) {
        inputs.files(templateSources)
            .withPropertyName("templateSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
    }
    if ("template-contract" in selectedRules) {
        inputs.property("templatesRootExists", providers.provider { templatesRoot.asFile.exists() })
    }
    if ("static-resource-contract" in selectedRules) {
        inputs.files(staticResourceSources)
            .withPropertyName("staticResourceSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
        inputs.property("staticRootExists", providers.provider { staticRoot.asFile.exists() })
        inputs.property(
            "baseTemplateExists",
            providers.provider { templatesRoot.file("base.html").asFile.exists() },
        )
    }
    if ("css-ownership" in selectedRules) {
        inputs.files(cssOwnershipSources)
            .withPropertyName("cssOwnershipSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
        inputs.property("cssRootExists", providers.provider { cssRoot.asFile.exists() })
    }
    if (selectedRules.any(setOf("raw-innerhtml", "layout-inline-style")::contains)) {
        inputs.files(staticJavaScriptSources)
            .withPropertyName("staticJavaScriptSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
    }
    if ("raw-innerhtml" in selectedRules) {
        inputs.files(testJavaScriptSources)
            .withPropertyName("testJavaScriptSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
        inputs.files(scriptJavaScriptSources)
            .withPropertyName("scriptJavaScriptSources")
            .withPathSensitivity(PathSensitivity.RELATIVE)
    }
    if (selectedRules.any(setOf("static-resource-contract", "raw-innerhtml", "layout-inline-style")::contains)) {
        if (baselineUpdateRules.get().isBlank()) {
            inputs.files(webQualityBaseline)
                .withPropertyName("webQualityBaseline")
                .withPathSensitivity(PathSensitivity.RELATIVE)
            inputs.property(
                "webQualityBaselineExists",
                providers.provider { webQualityBaseline.asFile.exists() },
            )
        } else {
            outputs.file(webQualityBaseline).withPropertyName("webQualityBaseline")
        }
    }
    inputs.property("rules", javaQualityRules)
    inputs.property("changedFiles", changedFiles)
    inputs.property("writeApiSnapshot", writeApiSnapshot)
    inputs.property("baselineUpdateRules", baselineUpdateRules)
    outputs.file(summary).withPropertyName("summary")
    if (writeApiSnapshot.get()) {
        outputs.file(apiSnapshot).withPropertyName("apiSnapshot")
    } else {
        inputs.file(apiSnapshot).withPropertyName("apiSnapshot").withPathSensitivity(PathSensitivity.RELATIVE)
    }
    if (baselineUpdateRules.get().isBlank() && "css-ownership" !in selectedRules) {
        outputs.cacheIf("deterministic quality report") { true }
    } else {
        outputs.cacheIf("execution-scoped output is not cacheable") { false }
        outputs.upToDateWhen { false }
    }

    val sourcePaths = linkedSetOf<File>()
    if (selectedRules.any(javaSourceRules::contains)) {
        sourcePaths.add(rootProject.file("java"))
    }
    if ("java-comment-language" in selectedRules) {
        sourcePaths.addAll(
            listOf(
                rootProject.file("java"),
                rootProject.file("gradle/build-logic"),
                rootProject.file("build.gradle.kts"),
                rootProject.file("settings.gradle.kts"),
            )
        )
    }
    if (selectedRules.any(setOf("template-contract", "static-resource-contract", "layout-inline-style")::contains)) {
        sourcePaths.add(templatesRoot.asFile)
    }
    if ("static-resource-contract" in selectedRules) {
        sourcePaths.add(staticRoot.asFile)
    }
    if ("css-ownership" in selectedRules) {
        sourcePaths.add(cssRoot.asFile)
    }
    if (selectedRules.any(setOf("raw-innerhtml", "layout-inline-style")::contains)) {
        sourcePaths.add(staticRoot.dir("js").asFile)
    }
    if ("raw-innerhtml" in selectedRules) {
        sourcePaths.add(rootProject.file("tests"))
        sourcePaths.add(rootProject.file("scripts"))
    }
    args(
        "--repo-root", rootProject.projectDir.absolutePath,
        "--paths", sourcePaths.joinToString(",") { it.absolutePath },
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
    if (baselineUpdateRules.get().isNotBlank()) {
        args("--update-baselines", baselineUpdateRules.get())
    }
}
