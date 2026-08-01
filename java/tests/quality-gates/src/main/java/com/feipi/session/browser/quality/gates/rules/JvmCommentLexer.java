package com.feipi.session.browser.quality.gates.rules;

import java.util.ArrayList;
import java.util.List;

/** 词法提取 Java、Kotlin 与 Gradle Kotlin 源码注释；不解释注释语言质量。 */
final class JvmCommentLexer {

  private JvmCommentLexer() {}

  /**
   * 提取行注释、块注释与 Javadoc，同时忽略字符串、字符和三引号 text block。
   *
   * @param text JVM 源码文本。
   * @return 按源码顺序排列的注释。
   */
  static List<SourceComment> extract(String text) {
    var comments = new ArrayList<SourceComment>();
    var state = State.NORMAL;
    var index = 0;
    var line = 1;
    var start = 0;
    var startLine = 1;
    var depth = 0;
    while (index < text.length()) {
      switch (state) {
        case NORMAL -> {
          if (startsWith(text, index, "\"\"\"")) {
            state = State.TEXT_BLOCK;
            index += 3;
          } else if (text.charAt(index) == '"') {
            state = State.STRING;
            index++;
          } else if (text.charAt(index) == '\'') {
            state = State.CHARACTER;
            index++;
          } else if (startsWith(text, index, "//")) {
            start = index;
            startLine = line;
            state = State.LINE_COMMENT;
            index += 2;
          } else if (startsWith(text, index, "/*")) {
            start = index;
            startLine = line;
            depth = 1;
            state = State.BLOCK_COMMENT;
            index += 2;
          } else {
            if (text.charAt(index) == '\n') {
              line++;
            }
            index++;
          }
        }
        case STRING, CHARACTER -> {
          var delimiter = state == State.STRING ? '"' : '\'';
          if (text.charAt(index) == '\\') {
            index = Math.min(text.length(), index + 2);
          } else {
            if (text.charAt(index) == '\n') {
              line++;
            }
            if (text.charAt(index) == delimiter) {
              state = State.NORMAL;
            }
            index++;
          }
        }
        case TEXT_BLOCK -> {
          if (startsWith(text, index, "\"\"\"")) {
            state = State.NORMAL;
            index += 3;
          } else {
            if (text.charAt(index) == '\n') {
              line++;
            }
            index++;
          }
        }
        case LINE_COMMENT -> {
          if (text.charAt(index) == '\n') {
            comments.add(
                new SourceComment(startLine, CommentKind.LINE, text.substring(start + 2, index)));
            state = State.NORMAL;
            line++;
          }
          index++;
        }
        case BLOCK_COMMENT -> {
          if (startsWith(text, index, "/*")) {
            depth++;
            index += 2;
          } else if (startsWith(text, index, "*/")) {
            depth--;
            var end = index;
            index += 2;
            if (depth == 0) {
              var kind = startsWith(text, start, "/**") ? CommentKind.JAVADOC : CommentKind.BLOCK;
              comments.add(new SourceComment(startLine, kind, text.substring(start + 2, end)));
              state = State.NORMAL;
            }
          } else {
            if (text.charAt(index) == '\n') {
              line++;
            }
            index++;
          }
        }
      }
    }
    if (state == State.LINE_COMMENT) {
      comments.add(new SourceComment(startLine, CommentKind.LINE, text.substring(start + 2)));
    }
    return List.copyOf(comments);
  }

  private static boolean startsWith(String text, int offset, String value) {
    return text.regionMatches(offset, value, 0, value.length());
  }

  /** JVM 源码注释类型。 */
  enum CommentKind {
    LINE,
    BLOCK,
    JAVADOC
  }

  /**
   * 单段 JVM 源码注释。
   *
   * @param line 注释起始行号（1-based）。
   * @param kind 注释类型。
   * @param text 去掉最外层注释定界符后的原文。
   */
  record SourceComment(int line, CommentKind kind, String text) {}

  /** 词法扫描器当前所在的源码区域。 */
  private enum State {
    NORMAL,
    STRING,
    CHARACTER,
    TEXT_BLOCK,
    LINE_COMMENT,
    BLOCK_COMMENT
  }
}
