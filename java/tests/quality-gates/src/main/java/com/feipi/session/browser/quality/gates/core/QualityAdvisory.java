package com.feipi.session.browser.quality.gates.core;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * 不阻断质量门的改进建议。
 *
 * @param rule 规则 id。
 * @param path 仓库相对 POSIX 路径。
 * @param line 建议所在行号（1-based）。
 * @param code 稳定建议代码。
 * @param message 用户可读说明。
 * @param attributes 附加属性。
 */
public record QualityAdvisory(
    String rule,
    String path,
    int line,
    String code,
    String message,
    Map<String, String> attributes) {

  /** 校验必填字段并做防御性复制。 */
  public QualityAdvisory {
    Objects.requireNonNull(rule, "rule");
    Objects.requireNonNull(path, "path");
    Objects.requireNonNull(code, "code");
    Objects.requireNonNull(message, "message");
    if (rule.isBlank() || line < 1 || code.isBlank() || message.isBlank()) {
      throw new IllegalArgumentException("advisory fields must be valid");
    }
    attributes =
        attributes == null
            ? Map.of()
            : Collections.unmodifiableMap(new LinkedHashMap<>(attributes));
  }
}
