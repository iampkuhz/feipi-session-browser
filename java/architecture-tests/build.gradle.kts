plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(project(":java:query-api"))
    testImplementation(project(":java:source-spi"))
    testImplementation(libs.archunit.junit5)
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testCompileOnly(libs.lombok)
    testAnnotationProcessor(libs.lombok)
}

tasks.withType<Test>().configureEach {
    systemProperty("repo.root.dir", rootProject.projectDir.absolutePath)
    jvmArgs("--add-modules", "jdk.compiler")
}
