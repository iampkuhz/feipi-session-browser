plugins {
    base
}

group = "com.feipi.session.browser"
version = file("VERSION").readText().trim()

subprojects {
    group = rootProject.group
    version = rootProject.version
}

dependencyLocking {
    lockAllConfigurations()
}

// Only leaf subprojects have check tasks.
val leafSubprojects by lazy { subprojects.filter { it.childProjects.isEmpty() } }

// Root `check` aggregates all subproject checks.
tasks.named("check") {
    dependsOn(leafSubprojects.map { "${it.path}:check" })
}

// ============================================================
// qualityFull – slow gate aggregating check + reports + fixtures
// ============================================================
val qualityFull = tasks.register("qualityFull") {
    group = "verification"
    description = "Full quality gate: check + root JaCoCo report + functional fixtures."
    dependsOn("check")
}

// ============================================================
// jacocoRootReport – aggregated JaCoCo coverage report
// ============================================================
val jacocoRootReport = tasks.register("jacocoRootReport") {
    group = "verification"
    description = "Aggregated JaCoCo report across all modules."
}

// Wire JaCoCo root report to depend on subproject JaCoCo reports
gradle.projectsEvaluated {
    jacocoRootReport.configure {
        dependsOn(leafSubprojects.mapNotNull { sub ->
            sub.tasks.names.takeIf { "jacocoTestReport" in it }
                ?.let { "${sub.path}:jacocoTestReport" }
        })
    }
    qualityFull.configure {
        dependsOn(jacocoRootReport)
    }
}

// ============================================================
// javadocVerify – aggregated Javadoc verification
// ============================================================
val javadocVerify = tasks.register("javadocVerify") {
    group = "verification"
    description = "Verifies Javadoc for all modules with production source code."
}

gradle.projectsEvaluated {
    javadocVerify.configure {
        dependsOn(leafSubprojects.filter { sub ->
            sub.file("src/main/java").exists()
        }.map { "${it.path}:javadoc" })
    }
}

tasks.named("check") {
    dependsOn(javadocVerify)
}

// ============================================================
// verifyNoSkippedJavaTests – zero skipped/aborted enforcement
// ============================================================
val verifyNoSkippedJavaTests = tasks.register("verifyNoSkippedJavaTests") {
    group = "verification"
    description = "Fails if any Java test has been skipped or aborted."
}

gradle.projectsEvaluated {
    verifyNoSkippedJavaTests.configure {
        dependsOn(leafSubprojects.mapNotNull { sub ->
            sub.tasks.names.takeIf { "test" in it }?.let { "${sub.path}:test" }
        })

        doLast {
            var totalSkipped = 0
            var totalErrors = 0
            var totalTests = 0
            var filesFound = 0

            leafSubprojects.forEach { sub ->
                val testResultsDir =
                    sub.layout.buildDirectory.dir("test-results/test").get().asFile
                if (testResultsDir.exists()) {
                    testResultsDir.walkTopDown()
                        .filter { it.name.startsWith("TEST-") && it.extension == "xml" }
                        .forEach { file ->
                            filesFound++
                            val content = file.readText()
                            val skippedMatch = Regex("""skipped="(\d+)"""").find(content)
                            val errorsMatch = Regex("""errors="(\d+)"""").find(content)
                            val testsMatch = Regex("""tests="(\d+)"""").find(content)
                            totalSkipped += skippedMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                            totalErrors += errorsMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                            totalTests += testsMatch?.groupValues?.get(1)?.toIntOrNull() ?: 0
                        }
                }
            }

            if (totalSkipped > 0) {
                throw GradleException(
                    "Found $totalSkipped skipped test(s). Skipped tests are not allowed."
                )
            }
            if (totalErrors > 0) {
                throw GradleException(
                    "Found $totalErrors aborted/errored test(s). Aborted tests are not allowed."
                )
            }
            if (filesFound == 0) {
                logger.lifecycle(
                    "verifyNoSkippedJavaTests: No test result XMLs found. " +
                        "This may be expected if no modules have test sources."
                )
            } else {
                logger.lifecycle(
                    "verifyNoSkippedJavaTests: $totalTests test(s) in $filesFound file(s), " +
                        "0 skipped, 0 aborted."
                )
            }
        }
    }
}

tasks.named("check") {
    dependsOn(verifyNoSkippedJavaTests)
}

// ============================================================
// verifyLeanQualityStack – ensure excluded tools are absent
// ============================================================
val verifyLeanQualityStack = tasks.register("verifyLeanQualityStack") {
    group = "verification"
    description = "Verifies that excluded quality tools are not present in the build."
    doLast {
        val catalogFile = file("gradle/libs.versions.toml")
        if (catalogFile.exists()) {
            val catalogContent = catalogFile.readText()
            val forbiddenEntries = listOf(
                "spotbugs-plugin", "forbiddenapis", "pitest", "cyclonedx",
                "errorprone", "nullaway", "spotbugs-annotations",
            )
            forbiddenEntries.forEach { entry ->
                if (catalogContent.contains(Regex("""\b${Regex.escape(entry)}\b"""))) {
                    throw GradleException("Version catalog contains excluded tool entry: $entry")
                }
            }
        }
        logger.lifecycle("verifyLeanQualityStack: PASSED – no excluded tools detected in catalog.")
    }
}

tasks.named("check") {
    dependsOn(verifyLeanQualityStack)
}

// ============================================================
// benchmark – independent lifecycle, dry-run only for now
// ============================================================
tasks.register("benchmark") {
    group = "benchmark"
    description = "Benchmark lifecycle. Placeholder until JMH provider is created."
}
