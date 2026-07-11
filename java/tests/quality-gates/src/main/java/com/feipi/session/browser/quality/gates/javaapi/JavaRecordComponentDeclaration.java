package com.feipi.session.browser.quality.gates.javaapi;

/**
 * Java record component 声明。
 *
 * @param name component 名称。
 * @param typeText component 类型文本。
 * @param line component 声明行号（1-based）。
 * @param startOffset component 在源文件中的字符偏移。
 */
public record JavaRecordComponentDeclaration(
    String name, String typeText, int line, int startOffset) {}
