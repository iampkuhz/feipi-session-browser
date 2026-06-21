import org.gradle.api.artifacts.VersionCatalogsExtension

plugins {
    id("com.diffplug.spotless")
    checkstyle
    pmd
}

// Access version catalog from the consuming project
val catalog = project.extensions.getByType<VersionCatalogsExtension>().named("libs")
val googleJavaFormatVersion = catalog.findVersion("google-java-format").get().requiredVersion
val checkstyleVersion = catalog.findVersion("checkstyle").get().requiredVersion
val pmdVersion = catalog.findVersion("pmd").get().requiredVersion

// ============================================================
// Spotless – single auto-formatting entry point
// ============================================================
spotless {
    java {
        target("src/*/java/**/*.java")
        googleJavaFormat(googleJavaFormatVersion)
        removeUnusedImports()
        trimTrailingWhitespace()
        endWithNewline()
    }

    kotlinGradle {
        target("*.gradle.kts")
        trimTrailingWhitespace()
        endWithNewline()
    }
}

// spotlessApply must NOT be wired to check. Only spotlessCheck.

// ============================================================
// Checkstyle
// ============================================================
checkstyle {
    toolVersion = checkstyleVersion
    configFile = project.rootProject.file("config/checkstyle/checkstyle.xml")
    isIgnoreFailures = false
    maxErrors = 0
    maxWarnings = 0
}

tasks.withType<Checkstyle>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

// ============================================================
// PMD – whitelist rules only
// ============================================================
pmd {
    toolVersion = pmdVersion
    ruleSetFiles = files(project.rootProject.file("config/pmd/pmd.xml"))
    ruleSets = listOf()
    isIgnoreFailures = false
    incrementalAnalysis = true
}

tasks.withType<Pmd>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

// ============================================================
// Javadoc / DocLint verification
// ============================================================
tasks.withType<Javadoc>().configureEach {
    val opts = options as StandardJavadocDocletOptions
    opts.encoding = "UTF-8"
    opts.docEncoding = "UTF-8"
    opts.charSet = "UTF-8"
    opts.memberLevel = JavadocMemberLevel.PRIVATE
    opts.addBooleanOption("Xdoclint:all,-missing", true)
    opts.addBooleanOption("Werror", true)
    opts.noTimestamp(true)
}
