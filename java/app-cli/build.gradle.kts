plugins {
    id("feipi.java-application")
}

application {
    mainClass.set("com.feipi.session.browser.cli.App")
}

dependencies {
    implementation(project(":java:core-domain"))
}
