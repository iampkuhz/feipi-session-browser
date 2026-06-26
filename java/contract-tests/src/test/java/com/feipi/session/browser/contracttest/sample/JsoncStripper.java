package com.feipi.session.browser.contracttest.sample;

import java.util.regex.Pattern;

/**
 * JSONC 注释剥离器。
 *
 * <p>移除 JSONC 格式中的 {@code //} 单行注释和 {@code /* ... * /} 多行注释， 返回纯 JSON 字符串。
 */
public final class JsoncStripper {

  private static final Pattern SINGLE_LINE_COMMENT = Pattern.compile("//.*$", Pattern.MULTILINE);
  private static final Pattern MULTI_LINE_COMMENT =
      Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL);

  private JsoncStripper() {}

  /**
   * 移除 JSONC 注释。
   *
   * @param jsonc 带注释的 JSONC 字符串
   * @return 纯 JSON 字符串
   */
  public static String strip(String jsonc) {
    if (jsonc == null || jsonc.isEmpty()) {
      return jsonc;
    }
    String result = MULTI_LINE_COMMENT.matcher(jsonc).replaceAll("");
    result = SINGLE_LINE_COMMENT.matcher(result).replaceAll("");
    return result.trim();
  }
}
