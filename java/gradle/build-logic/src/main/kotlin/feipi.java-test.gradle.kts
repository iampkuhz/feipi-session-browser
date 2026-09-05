plugins {
    `java-library`
    id("feipi.java-base")
    id("feipi.java-quality")
}

// --- 所有测试任务使用 JUnit Platform ---
dependencies {
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = false
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
    reports {
        junitXml.required.set(true)
        html.required.set(true)
    }
}

// --- JaCoCo 覆盖率 ---
apply(plugin = "jacoco")

tasks.withType<JacocoReport>().configureEach {
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}
