import org.gradle.api.artifacts.VersionCatalogsExtension

plugins {
    id("com.diffplug.spotless")
    checkstyle
    pmd
}

// 从消费项目的版本目录获取工具版本号
val catalog = project.extensions.getByType<VersionCatalogsExtension>().named("libs")
val googleJavaFormatVersion = catalog.findVersion("google-java-format").get().requiredVersion
val checkstyleVersion = catalog.findVersion("checkstyle").get().requiredVersion
val pmdVersion = catalog.findVersion("pmd").get().requiredVersion

// ============================================================
// Spotless —— 统一自动格式化入口
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

// spotlessApply 不能挂到 check，只挂 spotlessCheck。

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
// Javadoc / DocLint 验证
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
