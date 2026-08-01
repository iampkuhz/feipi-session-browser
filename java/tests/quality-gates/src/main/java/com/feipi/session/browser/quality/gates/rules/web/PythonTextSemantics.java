package com.feipi.session.browser.quality.gates.rules.web;

import java.util.ArrayList;
import java.util.List;

/** 保留旧 Python scanner 的 Unicode 空白与 {@code splitlines()} 边界。 */
final class PythonTextSemantics {

  /** Python {@code re} 默认 {@code \s} 接受的字符集合。 */
  static final String WHITESPACE_CLASS =
      "[\\u0009-\\u000D\\u001C-\\u0020\\u0085\\u00A0\\u1680"
          + "\\u2000-\\u200A\\u2028\\u2029\\u202F\\u205F\\u3000]";

  private PythonTextSemantics() {}

  /** 按 Python {@code str.splitlines()} 的 11 类边界拆行，不保留行尾字符。 */
  static List<String> splitLines(String text) {
    if (text.isEmpty()) {
      return List.of();
    }
    var lines = new ArrayList<String>();
    var start = 0;
    var index = 0;
    while (index < text.length()) {
      var boundaryLength = boundaryLength(text, index);
      if (boundaryLength == 0) {
        index += Character.charCount(text.codePointAt(index));
        continue;
      }
      lines.add(text.substring(start, index));
      index += boundaryLength;
      start = index;
    }
    if (start < text.length()) {
      lines.add(text.substring(start));
    }
    return List.copyOf(lines);
  }

  /** 按 Python {@code str.strip()} 的 Unicode 空白集合裁剪两端。 */
  static String strip(String value) {
    var start = 0;
    var end = value.length();
    while (start < end) {
      var codePoint = value.codePointAt(start);
      if (!isWhitespace(codePoint)) {
        break;
      }
      start += Character.charCount(codePoint);
    }
    while (end > start) {
      var codePoint = value.codePointBefore(end);
      if (!isWhitespace(codePoint)) {
        break;
      }
      end -= Character.charCount(codePoint);
    }
    return value.substring(start, end);
  }

  private static int boundaryLength(String text, int index) {
    var current = text.charAt(index);
    if (current == '\r') {
      return index + 1 < text.length() && text.charAt(index + 1) == '\n' ? 2 : 1;
    }
    return switch (current) {
      case '\n', '\u000B', '\f', '\u001C', '\u001D', '\u001E', '\u0085', '\u2028', '\u2029' -> 1;
      default -> 0;
    };
  }

  private static boolean isWhitespace(int codePoint) {
    return (codePoint >= 0x0009 && codePoint <= 0x000D)
        || (codePoint >= 0x001C && codePoint <= 0x0020)
        || codePoint == 0x0085
        || codePoint == 0x00A0
        || codePoint == 0x1680
        || (codePoint >= 0x2000 && codePoint <= 0x200A)
        || codePoint == 0x2028
        || codePoint == 0x2029
        || codePoint == 0x202F
        || codePoint == 0x205F
        || codePoint == 0x3000;
  }
}
