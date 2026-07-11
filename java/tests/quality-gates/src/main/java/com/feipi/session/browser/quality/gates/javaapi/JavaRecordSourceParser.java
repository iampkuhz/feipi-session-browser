package com.feipi.session.browser.quality.gates.javaapi;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Java record 源码解析器。
 *
 * <p>从 Java 源文件中提取 record 声明、component 列表和类型 Javadoc。 采用源码文本分析方式，不要求源文件可编译。
 *
 * <p>支持：public/package-private record、annotated record、generic record、 nested record、record
 * implements Interface。
 */
public final class JavaRecordSourceParser {

  private static final Set<String> JAVA_MODIFIERS =
      Set.of(
          "public",
          "protected",
          "private",
          "abstract",
          "static",
          "final",
          "strictfp",
          "sealed",
          "non-sealed");

  private static final Pattern RECORD_PATTERN =
      Pattern.compile("\\brecord\\s+([A-Za-z_$][A-Za-z0-9_$]*)");

  private static final Pattern IDENT_PATTERN = Pattern.compile("[A-Za-z_$][A-Za-z0-9_$]*");

  private static final Pattern QUALIFIED_IDENT =
      Pattern.compile("[A-Za-z_$][A-Za-z0-9_$]*(\\s*\\.\\s*[A-Za-z_$][A-Za-z0-9_$]*)*");

  /**
   * 解析源文件中的所有 record 声明。
   *
   * @param sourceFile 源文件路径。
   * @return record 声明列表。
   * @throws IOException 读取失败时抛出。
   */
  public List<JavaRecordDeclaration> parse(Path sourceFile) throws IOException {
    var text = Files.readString(sourceFile, StandardCharsets.UTF_8);
    return parseSource(sourceFile, text);
  }

  /**
   * 从源码字符串中解析所有 record 声明。
   *
   * @param sourceFile 源文件路径（用于记录到声明中）。
   * @param source 源码文本。
   * @return record 声明列表。
   */
  public List<JavaRecordDeclaration> parseSource(Path sourceFile, String source) {
    var maskedResult = maskSource(source);
    var masked = maskedResult.masked;
    var javadocs = maskedResult.javadocs;

    var records = new ArrayList<JavaRecordDeclaration>();
    var matcher = RECORD_PATTERN.matcher(masked);

    while (matcher.find()) {
      var name = matcher.group(1);
      var recordStart = matcher.start();
      var afterName = matcher.end();

      // 跳过可选的类型参数 <T, U>
      var pos = skipTypeParams(masked, afterName);
      pos = skipSpace(masked, pos);

      // 必须有 '('
      if (pos >= masked.length() || masked.charAt(pos) != '(') {
        continue;
      }

      // 找匹配的 ')'
      var close = findMatching(masked, pos, '(', ')');
      if (close < 0) {
        continue;
      }

      // 提取 components
      var rawBetween = source.substring(pos + 1, close);
      var componentBaseOffset = pos + 1;
      var components = splitComponents(rawBetween, componentBaseOffset, source, javadocs);

      // 找类型 Javadoc
      var javadoc = findNearestJavadoc(masked, javadocs, recordStart);

      records.add(
          new JavaRecordDeclaration(
              sourceFile, name, lineOf(source, recordStart), recordStart, javadoc, components));
    }

    return records;
  }

  // ---- 内部辅助方法 ----

  /** 将源码中的注释和字符串掩码为空格，保留换行符。同时收集 Javadoc 块。 */
  private static MaskedResult maskSource(String text) {
    var chars = text.toCharArray();
    var javadocs = new ArrayList<JavadocBlock>();
    var i = 0;
    var n = text.length();

    while (i < n) {
      if (text.startsWith("//", i)) {
        var start = i;
        i += 2;
        while (i < n && text.charAt(i) != '\n') {
          i++;
        }
        maskChars(chars, start, i);
        continue;
      }
      if (text.startsWith("/*", i)) {
        var start = i;
        i += 2;
        while (i < n && !text.startsWith("*/", i)) {
          i++;
        }
        var end = Math.min(n, i + 2);
        if (text.startsWith("/**", start)) {
          javadocs.add(
              new JavadocBlock(start, end, lineOf(text, start), text.substring(start, end)));
        } else {
          // /* */ 注释在 record 参数列表中也被视为有效文档
          javadocs.add(
              new JavadocBlock(start, end, lineOf(text, start), text.substring(start, end)));
        }
        maskChars(chars, start, end);
        i = end;
        continue;
      }
      if (text.startsWith("\"\"\"", i)) {
        var start = i;
        i += 3;
        while (i < n && !text.startsWith("\"\"\"", i)) {
          i++;
        }
        maskChars(chars, start, Math.min(n, i + 3));
        i = Math.min(n, i + 3);
        continue;
      }
      var ch = text.charAt(i);
      if (ch == '"' || ch == '\'') {
        var quote = ch;
        var start = i;
        i++;
        while (i < n) {
          if (text.charAt(i) == '\\') {
            i += 2;
            continue;
          }
          if (text.charAt(i) == quote) {
            i++;
            break;
          }
          i++;
        }
        maskChars(chars, start, i);
        continue;
      }
      i++;
    }

    return new MaskedResult(new String(chars), javadocs);
  }

  private static void maskChars(char[] chars, int start, int end) {
    for (var idx = start; idx < Math.min(end, chars.length); idx++) {
      if (chars[idx] != '\n') {
        chars[idx] = ' ';
      }
    }
  }

  private static int skipSpace(String text, int pos) {
    while (pos < text.length() && Character.isWhitespace(text.charAt(pos))) {
      pos++;
    }
    return pos;
  }

  private static int skipTypeParams(String masked, int pos) {
    pos = skipSpace(masked, pos);
    if (pos < masked.length() && masked.charAt(pos) == '<') {
      var close = findMatching(masked, pos, '<', '>');
      if (close >= 0) {
        return close + 1;
      }
    }
    return pos;
  }

  static int findMatching(String text, int openIndex, char openChar, char closeChar) {
    var depth = 0;
    for (var index = openIndex; index < text.length(); index++) {
      var ch = text.charAt(index);
      if (ch == openChar) {
        depth++;
      } else if (ch == closeChar) {
        depth--;
        if (depth == 0) {
          return index;
        }
      }
    }
    return -1;
  }

  /** 分割 record header 中的 component 列表。 */
  private static List<JavaRecordComponentDeclaration> splitComponents(
      String rawComponents, int baseOffset, String original, List<JavadocBlock> fileJavadocs) {
    var result = new ArrayList<JavaRecordComponentDeclaration>();
    var start = 0;
    var angle = 0;
    var paren = 0;
    var bracket = 0;
    var brace = 0;

    for (var index = 0; index < rawComponents.length(); index++) {
      var ch = rawComponents.charAt(index);
      switch (ch) {
        case '<' -> angle++;
        case '>' -> {
          if (angle > 0) angle--;
        }
        case '(' -> paren++;
        case ')' -> {
          if (paren > 0) paren--;
        }
        case '[' -> bracket++;
        case ']' -> {
          if (bracket > 0) bracket--;
        }
        case '{' -> brace++;
        case '}' -> {
          if (brace > 0) brace--;
        }
        case ',' -> {
          if (angle == 0 && paren == 0 && bracket == 0 && brace == 0) {
            var piece = rawComponents.substring(start, index).trim();
            if (!piece.isEmpty()) {
              var absStart = baseOffset + findPieceStart(rawComponents, start);
              extractComponent(piece, absStart, original, fileJavadocs).ifPresent(result::add);
            }
            start = index + 1;
          }
        }
        default -> {
          /* 忽略其他字符 */
        }
      }
    }

    // 最后一个 component
    var piece = rawComponents.substring(start).trim();
    if (!piece.isEmpty()) {
      var absStart = baseOffset + findPieceStart(rawComponents, start);
      extractComponent(piece, absStart, original, fileJavadocs).ifPresent(result::add);
    }

    return result;
  }

  private static int findPieceStart(String raw, int trimmedStart) {
    // 找到 trimmed start 在 raw 中的实际位置
    for (var i = trimmedStart; i < raw.length(); i++) {
      if (!Character.isWhitespace(raw.charAt(i))) {
        return i;
      }
    }
    return trimmedStart;
  }

  private static Optional<JavaRecordComponentDeclaration> extractComponent(
      String rawText, int absStart, String original, List<JavadocBlock> fileJavadocs) {
    var name = componentName(rawText);
    if (name == null) {
      return Optional.empty();
    }

    // 提取类型文本（component 名称之前的部分）
    var typeText = extractTypeText(rawText, name);
    var componentLine = lineOf(original, absStart);

    return Optional.of(new JavaRecordComponentDeclaration(name, typeText, componentLine, absStart));
  }

  static String componentName(String component) {
    var star = component.indexOf("*/");
    String searchIn;
    if (star >= 0) {
      searchIn = component.substring(star + 2);
    } else {
      searchIn = component;
    }
    var matcher = IDENT_PATTERN.matcher(searchIn);
    String last = null;
    while (matcher.find()) {
      last = matcher.group();
    }
    return last;
  }

  private static String extractTypeText(String component, String name) {
    // 移除 Javadoc
    var cleaned = component.replaceAll("/\\*.*?\\*/", "").trim();
    // 移除注解
    cleaned = removeAnnotations(cleaned).trim();
    // 移除最后的 component 名称
    var nameIdx = cleaned.lastIndexOf(name);
    if (nameIdx > 0) {
      return cleaned.substring(0, nameIdx).trim();
    }
    return "";
  }

  private static String removeAnnotations(String text) {
    var sb = new StringBuilder();
    var i = 0;
    while (i < text.length()) {
      if (text.charAt(i) == '@') {
        i++;
        // 跳过注解名称
        var m = QUALIFIED_IDENT.matcher(text.substring(i));
        if (m.lookingAt()) {
          i += m.end();
        }
        i = skipSpace(text, i);
        // 跳过注解参数
        if (i < text.length() && text.charAt(i) == '(') {
          var close = findMatching(text, i, '(', ')');
          if (close >= 0) {
            i = close + 1;
          }
        }
      } else {
        sb.append(text.charAt(i));
        i++;
      }
    }
    return sb.toString();
  }

  /** 查找 record 声明前的类型 Javadoc。 */
  private static Optional<String> findNearestJavadoc(
      String masked, List<JavadocBlock> javadocs, int recordStart) {
    for (var i = javadocs.size() - 1; i >= 0; i--) {
      var block = javadocs.get(i);
      if (block.end > recordStart) {
        continue;
      }
      var between = masked.substring(block.end, recordStart);
      if (between.isBlank() || onlyAnnotationsAndModifiers(between)) {
        return Optional.of(block.text);
      }
      return Optional.empty();
    }
    return Optional.empty();
  }

  /** 判断片段是否只包含注解和 Java 修饰符。 */
  private static boolean onlyAnnotationsAndModifiers(String segment) {
    var pos = 0;
    var n = segment.length();

    while (true) {
      pos = skipSpace(segment, pos);
      if (pos >= n) {
        return true;
      }
      if (segment.charAt(pos) == '@') {
        pos++;
        var m = QUALIFIED_IDENT.matcher(segment.substring(pos));
        if (!m.lookingAt()) {
          return false;
        }
        pos += m.end();
        pos = skipSpace(segment, pos);
        if (pos < n && segment.charAt(pos) == '(') {
          var close = findMatching(segment, pos, '(', ')');
          if (close < 0) {
            return false;
          }
          pos = close + 1;
        }
        continue;
      }
      var m = IDENT_PATTERN.matcher(segment.substring(pos));
      if (m.lookingAt() && JAVA_MODIFIERS.contains(m.group())) {
        pos += m.end();
        continue;
      }
      return false;
    }
  }

  static int lineOf(String text, int pos) {
    var line = 1;
    for (var i = 0; i < Math.min(pos, text.length()); i++) {
      if (text.charAt(i) == '\n') {
        line++;
      }
    }
    return line;
  }

  // ---- 内部数据类 ----

  /**
   * 掩码结果。
   *
   * @param masked 掩码后的源码文本。
   * @param javadocs 提取到的 Javadoc 块列表。
   */
  private record MaskedResult(String masked, List<JavadocBlock> javadocs) {}

  /**
   * Javadoc 注释块。
   *
   * @param start 起始字符偏移。
   * @param end 结束字符偏移。
   * @param line 起始行号。
   * @param text 注释原文。
   */
  record JavadocBlock(int start, int end, int line, String text) {}
}
