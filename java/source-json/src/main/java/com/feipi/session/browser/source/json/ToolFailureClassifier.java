package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 工具失败分类器。
 *
 * <p>基于文本启发式检测工具结果是否为运行时失败，与 Python 主实现的 {@code _tool_result_looks_failed()} 函数对齐。
 *
 * <p>分类策略：
 *
 * <ul>
 *   <li>文件操作工具（Read/Write/Edit/Glob/Grep/LS）：仅检查首行是否包含文件系统错误
 *   <li>其他工具：检查任意行是否包含运行时错误标记
 * </ul>
 */
public final class ToolFailureClassifier {

  /** 需要进行首行文件系统错误检查的工具名称集合。 */
  private static final Set<String> FILE_SYSTEM_TOOLS =
      Set.of("Read", "Write", "Edit", "Glob", "Grep", "LS");

  /** 文件系统错误标记，仅用于文件操作工具的首行检查。 */
  private static final String[] FS_ERROR_MARKERS = {
    "file does not exist",
    "permission denied",
    "no such file",
    "directory not found",
    "path not found",
    "cannot read",
    "not a directory",
    "too many levels of symbolic links",
    "input/output error",
    "is a directory"
  };

  /** 运行时错误标记，用于非文件操作工具的任意行检查。 */
  private static final String[] RUNTIME_ERROR_MARKERS = {
    "api error",
    "tool_use_error",
    "key_model_access_denied",
    "rate limit exceeded",
    "user rejected",
    "request cancelled",
    "permission denied",
    "fatal:"
  };

  private static final Pattern COMMAND_NOT_FOUND_AT_LINE_START =
      Pattern.compile("(?:^|\\n)\\s*command not found", Pattern.MULTILINE);
  private static final Pattern SHELL_COMMAND_NOT_FOUND =
      Pattern.compile("^(?:ba)?sh:\\s+.*:\\s+command not found");
  private static final Pattern TIMEOUT_AT_LINE_START =
      Pattern.compile("(?:^|\\n)\\s*timeout\\b", Pattern.MULTILINE);

  /** 防止实例化。 */
  private ToolFailureClassifier() {}

  /**
   * 检查工具结果内容是否表示运行时失败。
   *
   * @param content 工具结果内容文本，null 或空串返回 false
   * @param toolName 工具名称，用于决定检查策略；null 或空串按通用工具处理
   * @return 内容包含失败标记时返回 true
   */
  public static boolean looksFailed(String content, String toolName) {
    if (content == null || content.isEmpty()) {
      return false;
    }

    String text = stringify(content);
    if (text.isEmpty()) {
      return false;
    }

    boolean isFsTool = isFileSystemTool(toolName);

    if (isFsTool) {
      return checkFirstLineFsErrors(text);
    } else {
      return checkRuntimeErrors(text, toolName != null && !toolName.isBlank());
    }
  }

  /**
   * 检查工具结果 JSON 内容是否表示运行时失败。
   *
   * <p>将 JSON 节点序列化为文本后调用 {@link #looksFailed(String, String)}。
   *
   * @param contentNode 工具结果内容 JSON 节点
   * @param toolName 工具名称
   * @return 内容包含失败标记时返回 true
   */
  public static boolean looksFailed(JsonNode contentNode, String toolName) {
    if (contentNode == null || contentNode.isNull()) {
      return false;
    }
    String text = stringifyNode(contentNode);
    return looksFailed(text, toolName);
  }

  private static boolean isFileSystemTool(String toolName) {
    if (toolName == null || toolName.isEmpty()) {
      return false;
    }
    return FILE_SYSTEM_TOOLS.contains(toolName);
  }

  /** 仅检查首行是否包含文件系统错误标记。 */
  private static boolean checkFirstLineFsErrors(String text) {
    String firstLine = text.contains("\n") ? text.substring(0, text.indexOf('\n')) : text;
    firstLine = firstLine.trim().toLowerCase(Locale.ROOT);
    if (firstLine.isEmpty()) {
      return false;
    }
    for (String marker : FS_ERROR_MARKERS) {
      if (firstLine.startsWith(marker)) {
        return true;
      }
    }
    return false;
  }

  /** 检查任意行是否包含运行时错误标记。 */
  private static boolean checkRuntimeErrors(String text, boolean allowLineMarkers) {
    String lowerText = text.toLowerCase(Locale.ROOT);

    // 检查文本整体是否以错误标记开头
    for (String marker : RUNTIME_ERROR_MARKERS) {
      if (lowerText.startsWith(marker)) {
        return true;
      }
    }

    // 逐行检查是否有行以错误标记开头
    if (allowLineMarkers) {
      String[] lines = text.split("\n");
      for (String line : lines) {
        String stripped = stripShellPrompt(line.trim()).toLowerCase(Locale.ROOT);
        if (stripped.isEmpty()) {
          continue;
        }
        for (String marker : RUNTIME_ERROR_MARKERS) {
          if (stripped.startsWith(marker)) {
            return true;
          }
        }
        String[] parts = stripped.split(": ");
        if (parts.length > 1) {
          String lastPart = parts[parts.length - 1].trim();
          for (String marker : RUNTIME_ERROR_MARKERS) {
            if (lastPart.startsWith(marker)) {
              return true;
            }
          }
        }
      }
    }

    // 检查特殊模式
    if (checkCommandNotFound(lowerText)) {
      return true;
    }
    if (checkTimeout(text)) {
      return true;
    }

    return false;
  }

  private static String stripShellPrompt(String value) {
    int start = 0;
    while (start < value.length()) {
      char c = value.charAt(start);
      if (c == '$' || c == '#' || Character.isWhitespace(c)) {
        start++;
      } else {
        break;
      }
    }
    return value.substring(start).trim();
  }

  /**
   * 检查 command not found 模式。
   *
   * <p>匹配形如 {@code bash: kubectl: command not found} 的 shell 前缀格式。
   */
  private static boolean checkCommandNotFound(String lowerText) {
    if (COMMAND_NOT_FOUND_AT_LINE_START.matcher(lowerText).find()) {
      return true;
    }
    for (String line : lowerText.split("\n")) {
      if (SHELL_COMMAND_NOT_FOUND.matcher(line.trim()).find()) {
        return true;
      }
    }
    return false;
  }

  /**
   * 检查超时标记。
   *
   * <p>匹配独立的 {@code timeout} 单词（前后为非字母数字、非下划线字符或行首行尾）。
   */
  private static boolean checkTimeout(String text) {
    return TIMEOUT_AT_LINE_START.matcher(text.toLowerCase(Locale.ROOT)).find();
  }

  /** 将 JSON 内容节点转换为纯文本。 */
  private static String stringify(String content) {
    return content;
  }

  /** 将 JSON 节点序列化为可读文本。 */
  private static String stringifyNode(JsonNode node) {
    if (node == null || node.isNull()) {
      return "";
    }
    if (node.isTextual()) {
      return node.asText();
    }
    if (node.isArray()) {
      StringBuilder sb = new StringBuilder();
      for (JsonNode element : node) {
        if (element == null || element.isNull()) {
          continue;
        }
        if (element.isTextual()) {
          if (!sb.isEmpty()) {
            sb.append("\n");
          }
          sb.append(element.asText());
        } else if (element.isObject()) {
          JsonNode textNode = element.get("text");
          if (textNode != null && textNode.isTextual()) {
            if (!sb.isEmpty()) {
              sb.append("\n");
            }
            sb.append(textNode.asText());
          } else {
            JsonNode contentNode = element.get("content");
            if (contentNode != null) {
              if (!sb.isEmpty()) {
                sb.append("\n");
              }
              sb.append(stringifyNode(contentNode));
            }
          }
        }
      }
      return sb.toString();
    }
    if (node.isObject()) {
      JsonNode text = node.get("text");
      if (text != null && text.isTextual()) {
        return text.asText();
      }
    }
    return node.toString();
  }
}
