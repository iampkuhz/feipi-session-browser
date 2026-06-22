plugins {
    id("feipi.java-application")
}

application {
    mainClass.set("com.feipi.session.browser.cli.App")
}

dependencies {
    implementation(project(":java:core-domain"))
    implementation(libs.picocli)
}

// ============================================================
// build-info.properties 生成
// ============================================================
val generateBuildInfo = tasks.register("generateBuildInfo") {
    val versionFile = rootProject.file("VERSION")
    val outputDir = layout.buildDirectory.dir("generated/build-info")
    inputs.file(versionFile)
    outputs.dir(outputDir)

    doLast {
        val version = versionFile.readText().trim()
        val propsDir = outputDir.get().asFile.resolve("com/feipi/session/browser/cli")
        propsDir.mkdirs()
        propsDir.resolve("build-info.properties").writeText(
            "app.version=$version\n" +
            "app.name=feipi-session-browser\n",
            Charsets.UTF_8,
        )
    }
}

sourceSets.main.configure {
    resources.srcDir(generateBuildInfo)
}

tasks.named("processResources") {
    dependsOn(generateBuildInfo)
}
