package com.feipi.session.browser.query.api;

import java.util.List;
import java.util.Objects;
import java.util.Set;

/**
 * 敏感字段可见性策略。
 *
 * <p>集中管理详情 API 中需要默认隐藏的字段集合。 单一 owner 控制全部敏感字段规则，避免多处分散判断。
 *
 * <p>不可变值对象，在 {@link PayloadVisibility#STANDARD} 模式下隐藏 {@link #sensitiveFields()} 中的所有字段。
 */
public final class SensitiveFieldPolicy {

  /** 默认的敏感字段名列表，对应 payload 中的 key。 */
  private static final Set<String> DEFAULT_SENSITIVE_FIELDS =
      Set.of(
          "api_key",
          "apiKey",
          "token",
          "access_token",
          "accessToken",
          "secret",
          "password",
          "authorization",
          "private_key",
          "privateKey");

  /** 共享的默认策略实例。 */
  public static final SensitiveFieldPolicy DEFAULT =
      new SensitiveFieldPolicy(DEFAULT_SENSITIVE_FIELDS, true);

  private final Set<String> sensitiveFields;
  private final boolean maskingEnabled;

  private SensitiveFieldPolicy(Set<String> sensitiveFields, boolean maskingEnabled) {
    this.sensitiveFields = Set.copyOf(sensitiveFields);
    this.maskingEnabled = maskingEnabled;
  }

  /**
   * 创建使用自定义敏感字段集合的策略。
   *
   * @param sensitiveFields 需要隐藏的字段名集合
   * @param maskingEnabled 是否启用 masking
   * @return 自定义策略实例
   */
  public static SensitiveFieldPolicy custom(Set<String> sensitiveFields, boolean maskingEnabled) {
    Objects.requireNonNull(sensitiveFields, "sensitiveFields 不得为 null");
    return new SensitiveFieldPolicy(sensitiveFields, maskingEnabled);
  }

  /**
   * 创建禁用 masking 的策略，用于 {@link PayloadVisibility#FULL} 模式。
   *
   * @return 不隐藏任何字段的策略实例
   */
  public static SensitiveFieldPolicy noMasking() {
    return new SensitiveFieldPolicy(Set.of(), false);
  }

  /**
   * 根据可见性枚举获取对应策略。
   *
   * @param visibility payload 可见性级别
   * @return 对应的敏感字段策略
   */
  public static SensitiveFieldPolicy fromVisibility(PayloadVisibility visibility) {
    return switch (visibility) {
      case STANDARD -> DEFAULT;
      case FULL -> noMasking();
    };
  }

  /**
   * 判断给定字段名是否为敏感字段。
   *
   * @param fieldName 待检查的字段名
   * @return 当 masking 启用且字段在敏感集合中时返回 true
   */
  public boolean isSensitive(String fieldName) {
    return maskingEnabled && sensitiveFields.contains(fieldName);
  }

  /**
   * 对文本内容应用敏感字段 masking。
   *
   * <p>将匹配敏感字段名的值替换为 {@code [REDACTED]}。本方法只处理 key=value 格式的字符串内容， 不解析 JSON 结构。
   *
   * @param content 待 masking 的文本内容
   * @return masking 后的内容；若 masking 未启用则原样返回
   */
  public String applyMasking(String content) {
    if (!maskingEnabled || content == null || content.isEmpty()) {
      return content;
    }
    String result = content;
    for (String field : sensitiveFields) {
      // 匹配 key=value 和 key: value 两种格式
      result = result.replaceAll("(?i)(" + escapeRegex(field) + ")\\s*[=:]\\s*[^\\s&'\"]+", "$1=[REDACTED]");
    }
    return result;
  }

  /** 返回敏感字段名集合的不可变视图。 */
  public Set<String> sensitiveFields() {
    return sensitiveFields;
  }

  /** 是否启用 masking。 */
  public boolean maskingEnabled() {
    return maskingEnabled;
  }

  private static String escapeRegex(String literal) {
    return java.util.regex.Pattern.quote(literal);
  }
}
