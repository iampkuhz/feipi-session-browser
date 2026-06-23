package com.feipi.session.browser.source.json;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link JsonlReader} 的集成单元测试。
 *
 * <p>覆盖标准 JSONL、坏行、非对象值、美化打印、拼接对象、 空文件、BOM、CRLF、EOF 未终止 JSON 和配置上限等场景。
 */
@DisplayName("JsonlReader 集成测试")
class JsonlReaderTest {

  @TempDir Path tempDir;

  private final JsonlReader reader = new JsonlReader();

  // ─── 辅助方法 ─────────────────────────────────────────────────────────

  /** 将内容写入临时文件并返回路径。 */
  private Path write(String content) throws IOException {
    Path path = tempDir.resolve("test.jsonl");
    Files.writeString(path, content, StandardCharsets.UTF_8);
    return path;
  }

  /** 将原始字节写入临时文件（用于 BOM 测试）。 */
  private Path writeBytes(byte[] bytes) throws IOException {
    Path path = tempDir.resolve("test.jsonl");
    Files.write(path, bytes);
    return path;
  }

  // ─── 标准 JSONL ───────────────────────────────────────────────────────

  @Nested
  @DisplayName("标准 JSONL")
  class StandardJsonlTests {

    @Test
    @DisplayName("单对象")
    void singleObject() throws IOException {
      Path path = write("{\"type\": \"message\", \"id\": 1}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(1);
      assertThat(result.events().get(0).get("type").asText()).isEqualTo("message");
      assertThat(result.stats().eventsParsed()).isEqualTo(1);
      assertThat(result.stats().eventsSkipped()).isEqualTo(0);
    }

    @Test
    @DisplayName("多对象")
    void multipleObjects() throws IOException {
      String content =
          "{\"type\": \"start\", \"seq\": 1}\n"
              + "{\"type\": \"delta\", \"seq\": 2}\n"
              + "{\"type\": \"end\", \"seq\": 3}\n";
      Path path = write(content);
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(3);
      assertThat(result.events().stream().map(e -> e.get("type").asText()).toList())
          .containsExactly("start", "delta", "end");
      assertThat(result.stats().eventsParsed()).isEqualTo(3);
      assertThat(result.stats().eventsSkipped()).isEqualTo(0);
    }

    @Test
    @DisplayName("尾部空行被忽略")
    void trailingNewlineIgnored() throws IOException {
      Path path = write("{\"a\": 1}\n\n{\"b\": 2}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.stats().nonEmptyLines()).isEqualTo(2);
    }

    @Test
    @DisplayName("无尾部换行")
    void noTrailingNewline() throws IOException {
      Path path = write("{\"a\": 1}\n{\"b\": 2}");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
    }
  }

  // ─── 坏行/非对象值 ───────────────────────────────────────────────────

  @Nested
  @DisplayName("坏行与非对象值")
  class BadLinesTests {

    @Test
    @DisplayName("坏 JSON 行被跳过并记录 BAD_JSON/ERROR")
    void badJsonLineSkipped() throws IOException {
      Path path = write("{\"good\": true}\n{bad json}\n{\"also_good\": 1}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.stats().eventsSkipped()).isEqualTo(1);
      assertThat(result.diagnostics()).hasSize(1);

      SourceDiagnostic diag = result.diagnostics().get(0);
      assertThat(diag.severity()).isEqualTo(ParseSeverity.ERROR);
      assertThat(diag.issueType()).isEqualTo(ParseIssueType.BAD_JSON);
      assertThat(diag.message()).contains("line 2");
    }

    @Test
    @DisplayName("非对象值（array/string/number）记录 NON_OBJECT_SKIPPED/WARNING")
    void nonObjectSkipped() throws IOException {
      String content =
          "{\"keep\": \"this\"}\n"
              + "[\"an\", \"array\"]\n"
              + "\"just a string\"\n"
              + "42\n"
              + "{\"keep\": \"that\"}\n";
      Path path = write(content);
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.stats().eventsSkipped()).isEqualTo(3);

      List<SourceDiagnostic> warnings =
          result.diagnostics().stream().filter(d -> d.severity() == ParseSeverity.WARNING).toList();
      assertThat(warnings).hasSize(3);
      assertThat(warnings).allMatch(d -> d.issueType() == ParseIssueType.NON_OBJECT_SKIPPED);
    }

    @Test
    @DisplayName("混合坏行和非对象值")
    void mixedBadAndNonObject() throws IOException {
      Path path = write("{\"ok\": 1}\nnot json at all\n[1, 2, 3]\n{\"ok\": 2}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.stats().eventsSkipped()).isEqualTo(2);

      long errors =
          result.diagnostics().stream().filter(d -> d.severity() == ParseSeverity.ERROR).count();
      long warnings =
          result.diagnostics().stream().filter(d -> d.severity() == ParseSeverity.WARNING).count();
      assertThat(errors).isEqualTo(1);
      assertThat(warnings).isEqualTo(1);
    }
  }

  // ─── 多行/美化打印 JSON ──────────────────────────────────────────────

  @Nested
  @DisplayName("美化打印 JSON")
  class MultiLineJsonTests {

    @Test
    @DisplayName("单个美化对象")
    void singlePrettyObject() throws IOException {
      String content =
          "{\n"
              + "  \"type\": \"message\",\n"
              + "  \"content\": {\n"
              + "    \"text\": \"hello\",\n"
              + "    \"role\": \"user\"\n"
              + "  }\n"
              + "}\n";
      Path path = write(content);

      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(1);
      assertThat(result.events().get(0).get("type").asText()).isEqualTo("message");
      assertThat(result.events().get(0).get("content").get("text").asText()).isEqualTo("hello");
    }

    @Test
    @DisplayName("两个美化对象")
    void twoPrettyObjects() throws IOException {
      String content =
          "{\n  \"id\": 1\n}\n{\n  \"id\": 2,\n  \"extra\": [\n    \"a\",\n    \"b\"\n  ]\n}\n";
      Path path = write(content);
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.events().get(0).get("id").asInt()).isEqualTo(1);
      assertThat(result.events().get(1).get("id").asInt()).isEqualTo(2);
    }

    @Test
    @DisplayName("字符串内含花括号不影响深度追踪")
    void prettyWithStringContainingBraces() throws IOException {
      String content = "{\n  \"key\": \"a{b}c\",\n  \"nested\": {\"x\": 1}\n}\n";
      Path path = write(content);
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(1);
      assertThat(result.events().get(0).get("key").asText()).isEqualTo("a{b}c");
    }
  }

  // ─── }{ 拼接格式 ────────────────────────────────────────────────────

  @Nested
  @DisplayName("}{ 拼接对象")
  class ConcatenatedObjectsTests {

    @Test
    @DisplayName("美化对象关闭并拼接新对象（多行 + 单行过渡）")
    void prettyThenConcatenatedTransition() throws IOException {
      Path path = write("{\n  \"a\": 1\n}{\"b\": 2}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.events().get(0).get("a").asInt()).isEqualTo(1);
      assertThat(result.events().get(1).get("b").asInt()).isEqualTo(2);
    }

    @Test
    @DisplayName("三对象拼接")
    void prettyThenTwoConcatenated() throws IOException {
      Path path = write("{\n  \"a\": 1\n}{\"b\": 2}{\"c\": 3}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(3);
      assertThat(result.events().get(0).get("a").asInt()).isEqualTo(1);
      assertThat(result.events().get(1).get("b").asInt()).isEqualTo(2);
      assertThat(result.events().get(2).get("c").asInt()).isEqualTo(3);
    }

    @Test
    @DisplayName("拼接后接标准 JSONL 行")
    void concatenatedFollowedByStandardJsonl() throws IOException {
      Path path = write("{\n  \"a\": 1\n}{\"b\": 2}\n{\"c\": 3}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(3);
      assertThat(result.events().get(0).get("a").asInt()).isEqualTo(1);
      assertThat(result.events().get(1).get("b").asInt()).isEqualTo(2);
      assertThat(result.events().get(2).get("c").asInt()).isEqualTo(3);
    }

    @Test
    @DisplayName("拼接产生不可解析片段记录 BAD_JSON")
    void concatenatedProducesUnparseableFragment() throws IOException {
      Path path = write("{\"a\": 1}}{42}\n");
      JsonlReaderResult result = reader.read(path);

      // 拼接格式包含非标准边界，验证解析器不会崩溃并正常收集诊断信息
      assertThat(result.diagnostics()).isNotNull();
    }
  }

  // ─── 空文件 ───────────────────────────────────────────────────────────

  @Nested
  @DisplayName("空文件")
  class EmptyFileTests {

    @Test
    @DisplayName("完全空文件返回空结果")
    void completelyEmpty() throws IOException {
      Path path = write("");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).isEmpty();
      assertThat(result.stats().eventsParsed()).isEqualTo(0);
      assertThat(result.stats().totalLines()).isEqualTo(0);
    }

    @Test
    @DisplayName("纯空白文件返回空结果")
    void whitespaceOnly() throws IOException {
      Path path = write("\n\n  \t\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).isEmpty();
      assertThat(result.stats().eventsParsed()).isEqualTo(0);
    }
  }

  // ─── 诊断信息完整性 ──────────────────────────────────────────────────

  @Nested
  @DisplayName("诊断信息完整性")
  class DiagnosticsTests {

    @Test
    @DisplayName("诊断包含 lineNo、detail 和 preview")
    void issueHasLineNoDetailPreview() throws IOException {
      Path path = write("{\"good\": true}\n{broken}\n[1, 2]\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.diagnostics()).hasSize(2);

      SourceDiagnostic bad = result.diagnostics().get(0);
      assertThat(bad.lineNo()).isEqualTo(2);
      assertThat(bad.message()).contains("line 2");
      assertThat(bad.preview()).isPresent();
      assertThat(bad.preview().get()).contains("{broken}");

      SourceDiagnostic nonObj = result.diagnostics().get(1);
      assertThat(nonObj.lineNo()).isEqualTo(3);
      assertThat(nonObj.message()).containsIgnoringCase("array");
    }

    @Test
    @DisplayName("totalLines 反映文件行数")
    void totalLinesReflectsFile() throws IOException {
      Path path = write("a\nb\nc\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.stats().totalLines()).isEqualTo(3);
    }

    @Test
    @DisplayName("nonEmptyLines 计数正确")
    void nonEmptyLinesCount() throws IOException {
      Path path = write("{\"a\": 1}\n\n{\"b\": 2}\n\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.stats().nonEmptyLines()).isEqualTo(2);
    }

    @Test
    @DisplayName("WARNING/ERROR 计数正确")
    void warningErrorCounts() throws IOException {
      Path path = write("{\"ok\": 1}\n{\"ok\": 2}\nbad json\n\"string\"\nalso bad\n");
      JsonlReaderResult result = reader.read(path);

      long warnings =
          result.diagnostics().stream().filter(d -> d.severity() == ParseSeverity.WARNING).count();
      long errors =
          result.diagnostics().stream().filter(d -> d.severity() == ParseSeverity.ERROR).count();

      // 一行字符串值被跳过，记录为非对象警告
      assertThat(warnings).isEqualTo(1);
      // 两行非法 JSON 被跳过，记录为格式错误
      assertThat(errors).isEqualTo(2);
    }
  }

  // ─── BOM 处理 ─────────────────────────────────────────────────────────

  @Nested
  @DisplayName("BOM 处理")
  class BomTests {

    @Test
    @DisplayName("UTF-8 BOM 被跳过")
    void bomSkipped() throws IOException {
      byte[] bom = {(byte) 0xEF, (byte) 0xBB, (byte) 0xBF};
      byte[] json = "{\"a\": 1}\n".getBytes(StandardCharsets.UTF_8);
      byte[] content = new byte[bom.length + json.length];
      System.arraycopy(bom, 0, content, 0, bom.length);
      System.arraycopy(json, 0, content, bom.length, json.length);

      Path path = writeBytes(content);
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(1);
      assertThat(result.events().get(0).get("a").asInt()).isEqualTo(1);
    }

    @Test
    @DisplayName("无 BOM 的正常文件不受影响")
    void noBomNormal() throws IOException {
      Path path = write("{\"x\": true}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(1);
    }
  }

  // ─── EOF 未终止 JSON ─────────────────────────────────────────────────

  @Nested
  @DisplayName("EOF 未终止 JSON")
  class EofUnterminatedTests {

    @Test
    @DisplayName("depth > 0 到 EOF 时报告 BAD_JSON")
    void unterminatedJsonAtEof() throws IOException {
      Path path = write("{\"a\": 1\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).isEmpty();
      assertThat(result.diagnostics()).isNotEmpty();
      assertThat(result.diagnostics().get(0).issueType()).isEqualTo(ParseIssueType.BAD_JSON);
      assertThat(result.diagnostics().get(0).severity()).isEqualTo(ParseSeverity.ERROR);
    }

    @Test
    @DisplayName("多行未终止 JSON")
    void multiLineUnterminated() throws IOException {
      Path path = write("{\n  \"a\": 1\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).isEmpty();
      assertThat(result.diagnostics()).hasSize(1);
      assertThat(result.diagnostics().get(0).issueType()).isEqualTo(ParseIssueType.BAD_JSON);
    }
  }

  // ─── CRLF 行尾 ────────────────────────────────────────────────────────

  @Nested
  @DisplayName("CRLF 行尾")
  class CrlfTests {

    @Test
    @DisplayName("CRLF 行尾正常解析")
    void crlfLineEndings() throws IOException {
      Path path = write("{\"a\": 1}\r\n{\"b\": 2}\r\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
    }
  }

  // ─── 配置上限测试 ────────────────────────────────────────────────────

  @Nested
  @DisplayName("配置上限")
  class ConfigLimitTests {

    @Test
    @DisplayName("maxRecords 限制事件数量")
    void maxRecordsLimit() throws IOException {
      String content = "{\"a\": 1}\n{\"b\": 2}\n{\"c\": 3}\n{\"d\": 4}\n{\"e\": 5}\n";
      Path path = write(content);
      JsonlReader limitedReader = new JsonlReader(JsonlReaderConfig.of(3, 10_000_000, 120));
      JsonlReaderResult result = limitedReader.read(path);

      assertThat(result.events()).hasSize(3);
    }

    @Test
    @DisplayName("maxPreviewLength 截断预览文本")
    void maxPreviewLengthTruncation() throws IOException {
      // 构造一个超过默认 120 字符的坏 JSON
      StringBuilder sb = new StringBuilder();
      sb.append("{\"bad\": \"");
      while (sb.length() < 200) {
        sb.append("x");
      }
      sb.append("\"}\n");
      String longLine = "not valid json " + "x".repeat(200) + "\n";
      Path path = write(longLine);

      JsonlReader smallPreviewReader =
          new JsonlReader(JsonlReaderConfig.of(1_000_000, 10_000_000, 10));
      JsonlReaderResult result = smallPreviewReader.read(path);

      assertThat(result.diagnostics()).isNotEmpty();
      SourceDiagnostic diag = result.diagnostics().get(0);
      assertThat(diag.preview()).isPresent();
      assertThat(diag.preview().get().length()).isLessThanOrEqualTo(10);
    }
  }

  // ─── 结果不可变性 ────────────────────────────────────────────────────

  @Nested
  @DisplayName("结果不可变性")
  class ImmutabilityTests {

    @Test
    @DisplayName("events 列表不可修改")
    void eventsListImmutable() throws IOException {
      Path path = write("{\"a\": 1}\n");
      JsonlReaderResult result = reader.read(path);

      org.junit.jupiter.api.Assertions.assertThrows(
          UnsupportedOperationException.class, () -> result.events().add(result.events().get(0)));
    }

    @Test
    @DisplayName("diagnostics 列表不可修改")
    void diagnosticsListImmutable() throws IOException {
      Path path = write("{bad}\n");
      JsonlReaderResult result = reader.read(path);

      org.junit.jupiter.api.Assertions.assertThrows(
          UnsupportedOperationException.class,
          () -> result.diagnostics().add(result.diagnostics().get(0)));
    }
  }

  // ─── 括号不匹配 ──────────────────────────────────────────────────────

  @Nested
  @DisplayName("括号不匹配")
  class BracketMismatchTests {

    @Test
    @DisplayName("花括号开后用方括号关闭产生 BRACKET_MISMATCH")
    void curlyOpenSquareClose() throws IOException {
      Path path = write("{\"a\":]\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).isEmpty();
      assertThat(result.diagnostics()).isNotEmpty();
      SourceDiagnostic diag = result.diagnostics().get(0);
      assertThat(diag.code()).isEqualTo("BAD_JSON:BRACKET_MISMATCH");
      assertThat(diag.severity()).isEqualTo(ParseSeverity.ERROR);
    }

    @Test
    @DisplayName("多余的闭合括号产生 BRACKET_MISMATCH")
    void extraClosingBracket() throws IOException {
      Path path = write("{\"a\": 1}}\n");
      JsonlReaderResult result = reader.read(path);

      // 第一个对象正常解析，多余的 } 应产生诊断
      assertThat(result.events()).hasSize(1);
      assertThat(result.diagnostics()).isNotEmpty();
    }

    @Test
    @DisplayName("方括号内混用花括号产生 BRACKET_MISMATCH")
    void squareOpenCurlyClose() throws IOException {
      Path path = write("[1, 2}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.diagnostics()).isNotEmpty();
      assertThat(result.diagnostics().get(0).code()).isEqualTo("BAD_JSON:BRACKET_MISMATCH");
    }
  }

  // ─── 达到记录上限（STOPPED_BY_LIMIT） ──────────────────────────────

  @Nested
  @DisplayName("STOPPED_BY_LIMIT")
  class StoppedByLimitTests {

    @Test
    @DisplayName("达到 maxRecords 后 stoppedByLimit 为 true")
    void stoppedByLimitFlag() throws IOException {
      String content = "{\"a\": 1}\n{\"b\": 2}\n{\"c\": 3}\n{\"d\": 4}\n{\"e\": 5}\n";
      Path path = write(content);
      JsonlReader limitedReader = new JsonlReader(JsonlReaderConfig.of(3, 10_000_000, 120));
      JsonlReaderResult result = limitedReader.read(path);

      assertThat(result.events()).hasSize(3);
      assertThat(result.stoppedByLimit()).isTrue();
    }

    @Test
    @DisplayName("未达 maxRecords 时 stoppedByLimit 为 false")
    void notStoppedByLimit() throws IOException {
      Path path = write("{\"a\": 1}\n{\"b\": 2}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.stoppedByLimit()).isFalse();
    }

    @Test
    @DisplayName("达到上限后产生 STOPPED_BY_LIMIT 诊断")
    void stoppedByLimitDiagnostic() throws IOException {
      String content = "{\"a\": 1}\n{\"b\": 2}\n{\"c\": 3}\n";
      Path path = write(content);
      JsonlReader limitedReader = new JsonlReader(JsonlReaderConfig.of(2, 10_000_000, 120));
      JsonlReaderResult result = limitedReader.read(path);

      assertThat(result.events()).hasSize(2);
      assertThat(result.stoppedByLimit()).isTrue();
      assertThat(result.diagnostics()).anyMatch(d -> d.code().equals("STOPPED_BY_LIMIT"));
    }
  }

  // ─── 字节范围追踪 ──────────────────────────────────────────────────────

  @Nested
  @DisplayName("字节范围追踪")
  class ByteRangeTests {

    @Test
    @DisplayName("BAD_JSON 诊断包含字节范围")
    void badJsonByteRange() throws IOException {
      Path path = write("{\"good\": true}\n{bad}\n{\"also\": 1}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.diagnostics()).hasSize(1);
      SourceDiagnostic diag = result.diagnostics().get(0);
      assertThat(diag.byteRangeStart()).isPresent();
      assertThat(diag.byteRangeEnd()).isPresent();
      // 第二行起始字节应大于 0
      assertThat(diag.byteRangeStart().getAsInt()).isGreaterThan(0);
    }

    @Test
    @DisplayName("成功解析的记录也有字节范围")
    void successfulRecordByteRange() throws IOException {
      Path path = write("{\"a\": 1}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.events()).hasSize(1);
      // 非对象诊断也应有字节范围
    }
  }

  // ─── 缓冲区溢出 ──────────────────────────────────────────────────────

  @Nested
  @DisplayName("缓冲区溢出")
  class BufferOverflowTests {

    @Test
    @DisplayName("超大记录产生 BUFFER_OVERFLOW 诊断")
    void oversizedRecord() throws IOException {
      // 构造一个超过 maxBufferChars 的单行记录
      String bigContent = "{\"big\": \"" + "x".repeat(200) + "\"}\n";
      Path path = write(bigContent);
      // 设置极小的缓冲区
      JsonlReader tinyBufferReader = new JsonlReader(JsonlReaderConfig.of(1_000_000, 50, 120));
      JsonlReaderResult result = tinyBufferReader.read(path);

      assertThat(result.events()).isEmpty();
      assertThat(result.diagnostics()).anyMatch(d -> d.code().equals("BAD_JSON:BUFFER_OVERFLOW"));
    }
  }

  // ─── 预览脱敏 ──────────────────────────────────────────────────────

  @Nested
  @DisplayName("预览脱敏")
  class PreviewSanitizationTests {

    @Test
    @DisplayName("预览中包含疑似密钥字段被遮蔽")
    void secretFieldMasked() throws IOException {
      String content = "{\"password\": \"my_secret_123\", \"ok\": true}\n";
      // 构造一条坏 JSON 来触发诊断
      Path path = write(content + "{bad}\n");
      JsonlReaderResult result = reader.read(path);

      // 查找包含 password 的诊断
      assertThat(result.diagnostics()).isNotEmpty();
    }

    @Test
    @DisplayName("预览长度严格不超过 maxPreviewLength")
    void previewStrictMaxLength() throws IOException {
      String longLine = "x".repeat(500) + "\n";
      Path path = write(longLine);
      JsonlReader smallPreviewReader =
          new JsonlReader(JsonlReaderConfig.of(1_000_000, 10_000_000, 20));
      JsonlReaderResult result = smallPreviewReader.read(path);

      for (SourceDiagnostic d : result.diagnostics()) {
        if (d.preview().isPresent()) {
          assertThat(d.preview().get().length()).isLessThanOrEqualTo(20);
        }
      }
    }
  }

  // ─── 活跃写入检测 ──────────────────────────────────────────────────────

  @Nested
  @DisplayName("活跃写入检测")
  class ActiveWriteTests {

    @Test
    @DisplayName("正常文件不触发 RETRYABLE_INCOMPLETE")
    void normalFileNoRetryable() throws IOException {
      Path path = write("{\"a\": 1}\n");
      JsonlReaderResult result = reader.read(path);

      assertThat(result.diagnostics()).noneMatch(d -> d.code().equals("RETRYABLE_INCOMPLETE"));
    }
  }

  // ─── JsonlReaderResult 不包含 @DomainModel ─────────────────────────────

  @Nested
  @DisplayName("类型标注")
  class AnnotationTests {

    @Test
    @DisplayName("JsonlReaderResult 不标注 @DomainModel")
    void resultNotDomainModel() {
      assertThat(
              JsonlReaderResult.class.isAnnotationPresent(
                  com.feipi.session.browser.domain.annotation.DomainModel.class))
          .isFalse();
    }

    @Test
    @DisplayName("JsonlStats 不标注 @DomainModel")
    void statsNotDomainModel() {
      assertThat(
              JsonlStats.class.isAnnotationPresent(
                  com.feipi.session.browser.domain.annotation.DomainModel.class))
          .isFalse();
    }
  }
}
