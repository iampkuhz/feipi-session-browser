package com.feipi.session.browser.source.common;

/** 源事件标题文本清洗工具。 */
public final class SourceTitleTexts {

  private SourceTitleTexts() {}

  /** 清洗命令包裹和标签噪声，返回可展示标题。 */
  public static String clean(String value) {
    if (value == null || value.isBlank()) {
      return "";
    }
    String message = between(value, "<command-message>", "</command-message>");
    if (!message.isBlank()) {
      return message.strip();
    }
    return value.replaceAll("<[^>]+>", " ").replaceAll("\\s+", " ").strip();
  }

  private static String between(String value, String start, String end) {
    int startIndex = value.indexOf(start);
    if (startIndex < 0) {
      return "";
    }
    int contentStart = startIndex + start.length();
    int endIndex = value.indexOf(end, contentStart);
    if (endIndex < 0) {
      return "";
    }
    return value.substring(contentStart, endIndex);
  }
}
