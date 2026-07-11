package com.feipi.session.browser.quality.gates.javaapi;

import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

/**
 * Java record 类型声明。
 *
 * @param path 源文件路径。
 * @param name record 类型名称。
 * @param line record 关键字所在行号（1-based）。
 * @param startOffset record 关键字字符偏移。
 * @param typeJavadoc record 类型 Javadoc 原文；不存在时为空。
 * @param components record component 列表。
 */
public record JavaRecordDeclaration(
    Path path,
    String name,
    int line,
    int startOffset,
    Optional<String> typeJavadoc,
    List<JavaRecordComponentDeclaration> components) {}
