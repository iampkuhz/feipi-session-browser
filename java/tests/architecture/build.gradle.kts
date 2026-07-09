plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(project(":java:application"))
    testImplementation(project(":java:core-domain"))
    testImplementation(project(":java:index-api"))
    testImplementation(project(":java:scan-engine"))
    testImplementation(project(":java:source-spi"))
    testImplementation(project(":java:web"))
    testImplementation("com.tngtech.archunit:archunit-junit5:1.4.2")
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
    testCompileOnly(libs.lombok)
    testAnnotationProcessor(libs.lombok)
}

tasks.withType<Test>().configureEach {
    systemProperty("repo.root.dir", rootProject.projectDir.absolutePath)
    jvmArgs("--add-modules", "jdk.compiler")
}
