package com.feipi.session.browser.quality.gates.core;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * 单条质量违规。
 *
 * @param rule 规则 id。
 * @param path 仓库相对 POSIX 路径。
 * @param line 违规行号（1-based）。
 * @param code 违规代码，例如 {@code RECORD_JAVADOC_MISSING}。
 * @param message 用户可读说明。
 * @param attributes 附加属性，例如 record 名称、component 名称。
 */
public record QualityViolation(
    String rule,
    String path,
    int line,
    String code,
    String message,
    Map<String, String> attributes) {

  /**
   * 规范构造器：校验必填字段并做防御性拷贝。
   *
   * @param rule 规则 id；不得为空。
   * @param path 仓库相对路径；不得为 null。
   * @param line 违规行号；必须 >= 1。
   * @param code 违规代码；不得为空白。
   * @param message 用户可读说明；不得为空白。
   * @param attributes 附加属性；null 转空不可变 map。
   */
  public QualityViolation {
    Objects.requireNonNull(rule, "rule");
    if (rule.isBlank()) {
      throw new IllegalArgumentException("rule must not be blank");
    }
    Objects.requireNonNull(path, "path");
    if (line < 1) {
      throw new IllegalArgumentException("line must be >= 1, got: " + line);
    }
    Objects.requireNonNull(code, "code");
    if (code.isBlank()) {
      throw new IllegalArgumentException("code must not be blank");
    }
    Objects.requireNonNull(message, "message");
    if (message.isBlank()) {
      throw new IllegalArgumentException("message must not be blank");
    }
    attributes =
        attributes == null
            ? Map.of()
            : Collections.unmodifiableMap(new LinkedHashMap<>(attributes));
  }
}
