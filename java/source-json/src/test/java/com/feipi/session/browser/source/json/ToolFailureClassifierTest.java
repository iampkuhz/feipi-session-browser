package com.feipi.session.browser.source.json;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link ToolFailureClassifier} 单元测试。
 *
 * <p>验证工具失败文本启发式分类器与 Python 主实现 {@code _tool_result_looks_failed()} 的行为对齐。
 */
@DisplayName("ToolFailureClassifier 工具失败分类器测试")
class ToolFailureClassifierTest {

  @Nested
  @DisplayName("空输入")
  class EmptyInputTests {

    @Test
    @DisplayName("null 内容返回 false")
    void nullContentReturnsFalse() {
      assertThat(ToolFailureClassifier.looksFailed((String) null, "Bash")).isFalse();
    }

    @Test
    @DisplayName("空内容返回 false")
    void emptyContentReturnsFalse() {
      assertThat(ToolFailureClassifier.looksFailed("", "Bash")).isFalse();
    }

    @Test
    @DisplayName("null JSON 节点返回 false")
    void nullJsonNodeReturnsFalse() {
      assertThat(ToolFailureClassifier.looksFailed((com.fasterxml.jackson.databind.JsonNode) null, "Bash"))
          .isFalse();
    }
  }

  @Nested
  @DisplayName("文件操作工具首行检查")
  class FileSystemToolTests {

    @Test
    @DisplayName("Read 工具首行 file does not exist 返回 true")
    void readToolFileDoesNotExist() {
      assertThat(ToolFailureClassifier.looksFailed("File does not exist: /tmp/foo", "Read")).isTrue();
    }

    @Test
    @DisplayName("Write 工具首行 permission denied 返回 true")
    void writeToolPermissionDenied() {
      assertThat(ToolFailureClassifier.looksFailed("Permission denied: /etc/hosts", "Write")).isTrue();
    }

    @Test
    @DisplayName("Edit 工具首行 no such file 返回 true")
    void editToolNoSuchFile() {
      assertThat(ToolFailureClassifier.looksFailed("No such file or directory", "Edit")).isTrue();
    }

    @Test
    @DisplayName("Glob 工具首行 directory not found 返回 true")
    void globToolDirectoryNotFound() {
      assertThat(ToolFailureClassifier.looksFailed("Directory not found: /missing", "Glob")).isTrue();
    }

    @Test
    @DisplayName("Grep 工具首行 path not found 返回 true")
    void grepToolPathNotFound() {
      assertThat(ToolFailureClassifier.looksFailed("Path not found: /missing", "Grep")).isTrue();
    }

    @Test
    @DisplayName("LS 工具首行 not a directory 返回 true")
    void lsToolNotADirectory() {
      assertThat(ToolFailureClassifier.looksFailed("Not a directory: /etc/hosts/foo", "LS")).isTrue();
    }

    @Test
    @DisplayName("Read 工具首行 too many levels of symbolic links 返回 true")
    void readToolTooManySymlinks() {
      assertThat(
              ToolFailureClassifier.looksFailed(
                  "Too many levels of symbolic links", "Read"))
          .isTrue();
    }

    @Test
    @DisplayName("Read 工具首行 input/output error 返回 true")
    void readToolIOError() {
      assertThat(ToolFailureClassifier.looksFailed("Input/output error", "Read")).isTrue();
    }

    @Test
    @DisplayName("Read 工具首行 is a directory 返回 true")
    void readToolIsADirectory() {
      assertThat(ToolFailureClassifier.looksFailed("Is a directory: /tmp", "Read")).isTrue();
    }

    @Test
    @DisplayName("Read 工具第二行有 file does not exist 但首行正常则返回 false")
    void readToolSecondLineErrorIgnored() {
      assertThat(
              ToolFailureClassifier.looksFailed(
                  "File content here\nfile does not exist", "Read"))
          .isFalse();
    }

    @Test
    @DisplayName("Read 工具正常内容返回 false")
    void readToolNormalContentReturnsFalse() {
      assertThat(ToolFailureClassifier.looksFailed("public class Foo { }", "Read")).isFalse();
    }

    @Test
    @DisplayName("未知工具名不触发文件系统检查")
    void unknownToolDoesNotTriggerFsCheck() {
      assertThat(
              ToolFailureClassifier.looksFailed(
                  "File does not exist\nSome content", "UnknownTool"))
          .isFalse();
    }
  }

  @Nested
  @DisplayName("通用工具运行时错误检查")
  class GenericToolRuntimeErrorTests {

    @Test
    @DisplayName("api error 开头返回 true")
    void apiErrorReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("API Error: something went wrong", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("tool_use_error 开头返回 true")
    void toolUseErrorReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("Tool_use_error: invalid parameter", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("key_model_access_denied 返回 true")
    void keyModelAccessDeniedReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("Key_model_access_denied: ...", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("rate limit exceeded 返回 true")
    void rateLimitExceededReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("Rate limit exceeded", "Bash")).isTrue();
    }

    @Test
    @DisplayName("user rejected 返回 true")
    void userRejectedReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("User rejected the tool execution", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("request cancelled 返回 true")
    void requestCancelledReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("Request cancelled by user", "Bash")).isTrue();
    }

    @Test
    @DisplayName("permission denied 返回 true")
    void permissionDeniedReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("Permission denied", "Bash")).isTrue();
    }

    @Test
    @DisplayName("fatal: 开头返回 true")
    void fatalPrefixReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("fatal: not a git repository", "Bash")).isTrue();
    }

    @Test
    @DisplayName("command not found 返回 true")
    void commandNotFoundReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("bash: kubectl: command not found", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("timeout 独立词返回 true")
    void timeoutWordReturnsTrue() {
      assertThat(ToolFailureClassifier.looksFailed("The operation timed out", "Bash")).isFalse();
      assertThat(ToolFailureClassifier.looksFailed("timeout: the command timed out", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("timeout 作为其他单词的一部分不匹配")
    void timeoutAsPartOfWordDoesNotMatch() {
      assertThat(ToolFailureClassifier.looksFailed("timeout_error happened", "Bash")).isFalse();
    }

    @Test
    @DisplayName("多行内容中某行以错误标记开头返回 true")
    void multiLineWithErrorMarkerReturnsTrue() {
      assertThat(
              ToolFailureClassifier.looksFailed(
                  "Some output\napi error: something\nmore output", "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("正常内容返回 false")
    void normalContentReturnsFalse() {
      assertThat(
              ToolFailureClassifier.looksFailed(
                  "Hello world\nThis is a normal output\nAll done", "Bash"))
          .isFalse();
    }

    @Test
    @DisplayName("空工具名按通用工具处理")
    void emptyToolNameUsesGenericCheck() {
      assertThat(ToolFailureClassifier.looksFailed("API Error: something", "")).isTrue();
    }

    @Test
    @DisplayName("null 工具名按通用工具处理")
    void nullToolNameUsesGenericCheck() {
      assertThat(ToolFailureClassifier.looksFailed("API Error: something", null)).isTrue();
    }
  }

  @Nested
  @DisplayName("JSON 节点内容")
  class JsonNodeTests {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Test
    @DisplayName("文本节点直接检查")
    void textNodeDirectCheck() {
      assertThat(
              ToolFailureClassifier.looksFailed(
                  MAPPER.getNodeFactory().textNode("API Error: something"), "Bash"))
          .isTrue();
    }

    @Test
    @DisplayName("数组节点拼接后检查")
    void arrayNodeConcatenatedCheck() {
      ArrayNode array = MAPPER.createArrayNode();
      array.add("normal line");
      array.add("api error: something");
      assertThat(ToolFailureClassifier.looksFailed(array, "Bash")).isTrue();
    }

    @Test
    @DisplayName("包含 text 字段的对象数组")
    void objectArrayWithTextField() {
      ArrayNode array = MAPPER.createArrayNode();
      ObjectNode block = MAPPER.createObjectNode();
      block.put("type", "text");
      block.put("text", "fatal: not a git repository");
      array.add(block);
      assertThat(ToolFailureClassifier.looksFailed(array, "Bash")).isTrue();
    }

    @Test
    @DisplayName("文件操作工具 JSON 数组只检查首行")
    void fsToolJsonArrayChecksFirstLineOnly() {
      ArrayNode array = MAPPER.createArrayNode();
      array.add("File does not exist: /tmp/foo");
      assertThat(ToolFailureClassifier.looksFailed(array, "Read")).isTrue();
    }

    @Test
    @DisplayName("文件操作工具 JSON 数组第二行错误忽略")
    void fsToolJsonArraySecondLineErrorIgnored() {
      ArrayNode array = MAPPER.createArrayNode();
      array.add("Normal content");
      array.add("file does not exist");
      assertThat(ToolFailureClassifier.looksFailed(array, "Read")).isFalse();
    }
  }
}
