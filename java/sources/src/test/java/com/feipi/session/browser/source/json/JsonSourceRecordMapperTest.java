package com.feipi.session.browser.source.json;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceOutcome;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

@DisplayName("JsonSourceRecordMapper 映射测试")
class JsonSourceRecordMapperTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @TempDir Path tempDir;

  @Test
  @DisplayName("assistant 事件提取 content 字段到 SourceRecord.content")
  void assistantEventExtractsContent() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "assistant",
              "message": {
                "role": "assistant",
                "content": [
                  {
                    "type": "text",
                    "text": "Hello world"
                  }
                ]
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("test.jsonl", 0, event, "assistant");
    SourceRecord record = records.get(0);

    assertThat(record.content()).isEqualTo("Hello world");
  }

  @Test
  @DisplayName("user 事件提取 content 字段到 SourceRecord.content")
  void userEventExtractsContent() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "user",
              "message": {
                "role": "user",
                "content": "User message text"
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("test.jsonl", 0, event, "user");
    SourceRecord record = records.get(0);

    assertThat(record.content()).isEqualTo("User message text");
  }

  @Test
  @DisplayName("纯 user/tool_result 事件按 tool_result 处理并提取嵌套工具结果字段")
  void pureUserToolResultReclassifiedAsToolResult() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "user",
              "message": {
                "content": [
                  {
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "is_error": true,
                    "content": "Permission denied"
                  }
                ]
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("session.jsonl", 4, event, "user");
    SourceRecord record = records.get(0);

    assertThat(record.eventType()).isEqualTo("tool_result");
    assertThat(record.toolUseId()).contains("toolu_1");
    assertThat(record.toolError()).contains("tool_error");
    assertThat(record.locator()).isEqualTo("session.jsonl#event[4]");
  }

  @Test
  @DisplayName("含真实文本的 user 事件不会因携带工具结果块而误判为 tool_result")
  void userTextPreventsToolResultReclassification() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "user",
              "message": {
                "content": [
                  {"type": "text", "text": "please continue"},
                  {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
                ]
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("session.jsonl", 5, event, "user");
    SourceRecord record = records.get(0);

    assertThat(record.eventType()).isEqualTo("user");
    assertThat(record.toolUseId()).isEmpty();
    assertThat(records).extracting(SourceRecord::eventType).containsExactly("user", "tool_result");
    assertThat(records).extracting(SourceRecord::content).containsExactly("please continue", "ok");
    assertThat(records.get(1).toolUseId()).contains("toolu_1");
  }

  @Test
  @DisplayName("assistant 事件优先使用 message.id 作为语义 turnId，并读取 metadata.model")
  void assistantUsesMessageIdTurnIdAndMetadataModel() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "assistant",
              "id": "transport-id",
              "metadata": {"model": "qwen"},
              "message": {
                "id": "semantic-turn",
                "content": [
                  {"type": "tool_use", "id": "toolu_2", "name": "Read"}
                ]
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("session.jsonl", 6, event, "assistant");
    SourceRecord record = records.get(0);

    assertThat(record.turnId()).contains("semantic-turn");
    assertThat(record.model()).contains("qwen");
    assertThat(record.toolCalls()).extracting("toolCallId").containsExactly("toolu_2");
    assertThat(record.toolCalls()).extracting("name").containsExactly("Read");
  }

  @Test
  @DisplayName("解析模板用已知 tool name 二次判定 tool_result，避免 Read 内容误报")
  void parserEnrichesToolResultFailureWithKnownToolName() throws IOException {
    Path file = tempDir.resolve("session.jsonl");
    Files.writeString(
        file,
        """
        {"type":"assistant","message":{"content":[{"type":"tool_use","id":"read_1","name":"Read"}]}}
        {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"read_1","content":"normal file content\\napi error: literal text"}]}}
        {"type":"assistant","message":{"content":[{"type":"tool_use","id":"agent_1","name":"Agent"}]}}
        {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"agent_1","content":"api error: runtime failed"}]}}
        """,
        StandardCharsets.UTF_8);
    SourceFingerprint fp =
        new SourceFingerprint(
            file.toString(),
            SourceId.CLAUDE_CODE,
            Files.size(file),
            1,
            Optional.empty(),
            Optional.empty());
    Candidate candidate = new Candidate(fp, "claude_code:test", "project", Map.of());

    SourceResult result =
        JsonCandidateParser.parse(
            candidate,
            null,
            new JsonlReader(),
            event -> event.get("type").asText(),
            (event, eventIndex, eventType, locator, diagnostics) -> {},
            (diagnostics, eventCount) -> {});

    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    SourceResult.Success success = (SourceResult.Success) result;
    assertThat(success.records().get(1).toolError()).isEmpty();
    assertThat(success.records().get(1).toolName()).contains("Read");
    assertThat(success.records().get(3).toolError()).contains("text_heuristic_failure");
    assertThat(success.records().get(3).toolName()).contains("Agent");
  }

  @Test
  void mixedBlocksPreserveOrderWhitespaceAndSingleUsage() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
        {"type":"user","usage":{"input_tokens":17,"output_tokens":3},"message":{"parts":[
          {"type":"tool_result","tool_use_id":"a","content":"  first  "},
          {"type":"text","text":"  "},
          {"type":"tool_result","tool_use_id":"b","is_error":true,"content":"last"}
        ]}}
        """);
    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("session.jsonl", 2, event, "user");
    assertThat(records)
        .extracting(SourceRecord::eventType)
        .containsExactly("tool_result", "user", "tool_result");
    assertThat(records)
        .extracting(SourceRecord::content)
        .containsExactly("  first  ", "  ", "last");
    assertThat(records)
        .extracting(SourceRecord::toolUseId)
        .containsExactly(Optional.of("a"), Optional.empty(), Optional.of("b"));
    assertThat(records.get(0).toolError()).isEmpty();
    assertThat(records.get(2).toolError()).contains("tool_error");
    assertThat(records.get(0).usage().inputTokens()).isEqualTo(17);
    assertThat(records.get(1).usage())
        .isEqualTo(com.feipi.session.browser.domain.source.SourceRecordUsage.empty());
    assertThat(records.get(2).usage())
        .isEqualTo(com.feipi.session.browser.domain.source.SourceRecordUsage.empty());
    assertThat(records).extracting(SourceRecord::locator).doesNotHaveDuplicates();
  }

  @Test
  void partsAndBlankContentAreNotDiscarded() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
        {"message":{"parts":[{"type":"text","text":"  "},{"text":" x "}]}}
        """);
    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("session.jsonl", 0, event, "assistant");
    assertThat(records).hasSize(1);
    assertThat(records.get(0).content()).isEqualTo("   x ");
  }

  @Test
  void parserDoesNotLeakFailureAcrossToolResults() throws IOException {
    Path file = tempDir.resolve("multiple-tools.jsonl");
    Files.writeString(
        file,
        """
        {"type":"assistant","message":{"content":[{"type":"tool_use","id":"a","name":"Agent"},{"type":"tool_use","id":"b","name":"Agent"}]}}
        {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"a","content":"completed"},{"type":"text","text":"continue"},{"type":"tool_result","tool_use_id":"b","content":"api error: failed"}]}}
        """,
        StandardCharsets.UTF_8);
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            file.toString(),
            SourceId.CLAUDE_CODE,
            Files.size(file),
            1,
            Optional.empty(),
            Optional.empty());
    SourceResult result =
        JsonCandidateParser.parse(
            new Candidate(fingerprint, "claude_code:test", "project", Map.of()),
            null,
            new JsonlReader(),
            event -> event.get("type").asText(),
            (event, eventIndex, eventType, locator, diagnostics) -> {},
            (diagnostics, eventCount) -> {});
    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    List<SourceRecord> records = ((SourceResult.Success) result).records();
    assertThat(records).hasSize(4);
    assertThat(records.get(1).toolError()).isEmpty();
    assertThat(records.get(1).content()).isEqualTo("completed");
    assertThat(records.get(2).eventType()).isEqualTo("user");
    assertThat(records.get(3).toolError()).contains("text_heuristic_failure");
  }

  @Test
  void singleToolBlockPreservesOuterErrorAndName() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
        {"type":"user","name":"Read","is_error":true,"message":{"content":[
          {"type":"tool_result","tool_use_id":"a","content":"failed"}
        ]}}
        """);
    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("session.jsonl", 0, event, "user");
    assertThat(records).hasSize(1);
    assertThat(records.get(0).toolError()).contains("tool_error");
    assertThat(records.get(0).toolName()).contains("Read");
  }
}
