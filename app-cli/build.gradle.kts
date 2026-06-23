// 历史根级 :app-cli 路径兼容入口；真实发行逻辑仍由 :java:app-cli 执行。

tasks.register("installDist") {
    group = "distribution"
    description = "代理到 :java:app-cli:installDist，保持历史 Gradle 路径兼容。"
    dependsOn(":java:app-cli:installDist")
}

tasks.register("distZip") {
    group = "distribution"
    description = "代理到 :java:app-cli:distZip，保持历史 Gradle 路径兼容。"
    dependsOn(":java:app-cli:distZip")
}

tasks.register("check") {
    group = "verification"
    description = "兼容 project 无独立校验；真实校验由 :java:app-cli:check 覆盖。"
    dependsOn(":java:app-cli:check")
}
