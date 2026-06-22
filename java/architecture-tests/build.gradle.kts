plugins {
    id("feipi.java-test")
}

dependencies {
    testImplementation(project(":java:core-domain"))
    testImplementation(libs.archunit.junit5)
    testImplementation(libs.junit.jupiter)
    testImplementation(libs.assertj.core)
}

tasks.withType<Test>().configureEach {
    systemProperty("repo.root.dir", rootProject.projectDir.absolutePath)
    jvmArgs("--add-modules", "jdk.compiler")
}
