package com.feipi.session.browser.quality.gates.core;

import java.nio.file.Path;

/**
 * 多规则共享的不可变执行上下文。
 *
 * @param repoRoot 仓库根目录。
 * @param sources 一次 compiler parse 的候选源码。
 * @param repositorySources 一次读取的仓库文本源码。
 * @param qualityArtifactDir 当前执行身份对应的质量产物根目录。
 */
public record QualityContext(
    Path repoRoot,
    JavaSourceSet sources,
    RepositorySourceSet repositorySources,
    Path qualityArtifactDir) {}
