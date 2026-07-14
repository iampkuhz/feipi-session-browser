package com.feipi.session.browser.quality.gates.core;

import java.nio.file.Path;

/**
 * 多规则共享的不可变执行上下文。
 *
 * @param repoRoot 仓库根目录。
 * @param sources 一次 compiler parse 的候选源码。
 * @param apiSnapshot Java public API 基线文件。
 * @param writeApiSnapshot 是否处于显式 baseline 维护模式。
 */
public record QualityContext(
    Path repoRoot, JavaSourceSet sources, Path apiSnapshot, boolean writeApiSnapshot) {}
