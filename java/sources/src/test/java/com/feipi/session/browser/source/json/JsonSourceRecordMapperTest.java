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
  void onlyExplicitTopLevelBooleanTrueDeclaresMetaContext() throws IOException {
    List<String> events =
        List.of(
            "{\"type\":\"user\",\"isMeta\":true,\"content\":\"  meta context\\n\"}",
            "{\"type\":\"user\",\"isMeta\":false,\"content\":\"ordinary\"}",
            "{\"type\":\"user\",\"isMeta\":\"true\",\"content\":\"ordinary\"}",
            "{\"type\":\"user\",\"isMeta\":1,\"content\":\"ordinary\"}",
            "{\"type\":\"user\",\"isMeta\":null,\"content\":\"ordinary\"}",
            "{\"type\":\"user\",\"message\":{\"isMeta\":true,\"content\":\"ordinary\"}}",
            "{\"type\":\"user\",\"metadata\":{\"isMeta\":true},\"content\":\"ordinary\"}",
            "{\"type\":\"user\",\"content\":\"ordinary\"}");
    for (int i = 0; i < events.size(); i++) {
      SourceRecord record =
          JsonSourceRecordMapper.toSourceRecords(
                  "synthetic.jsonl", i, MAPPER.readTree(events.get(i)), "user")
              .getFirst();
      assertThat(record.metaContext()).as("synthetic variant %s", i).isEqualTo(i == 0);
      assertThat(record.eventType()).isEqualTo("user");
      assertThat(record.content()).isEqualTo(i == 0 ? "  meta context\n" : "ordinary");
      assertThat(record.locator()).isEqualTo("synthetic.jsonl#event[" + i + "]");
    }
  }

  @Test
  void metaMixedBlocksAndParserToolEnrichmentKeepEvidenceAndContent() throws IOException {
    Path file = tempDir.resolve("synthetic-meta-blocks.jsonl");
    Files.writeString(
        file,
        """
        {"type":"assistant","message":{"content":[{"type":"tool_use","id":"synthetic-read","name":"Read","input":{}}]}}
        {"type":"user","isMeta":true,"usage":{"input_tokens":17,"output_tokens":3},"message":{"content":[{"type":"text","text":"  meta before\\n"},{"type":"tool_result","tool_use_id":"synthetic-read","is_error":true,"content":"synthetic failure"},{"type":"text","text":"meta after  "}]}}
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
    SourceResult.Success result =
        (SourceResult.Success)
            JsonCandidateParser.parse(
                new Candidate(
                    fingerprint, "claude_code:synthetic-meta", "synthetic-project", Map.of()),
                null,
                new JsonlReader(),
                event -> event.path("type").asText(),
                (event, index, type, locator, diagnostics) -> {},
                (diagnostics, count) -> {});
    List<SourceRecord> records = result.records().subList(1, 4);
    assertThat(records).extracting(SourceRecord::metaContext).containsExactly(true, true, true);
    assertThat(records)
        .extracting(SourceRecord::eventType)
        .containsExactly("user", "tool_result", "user");
    assertThat(records)
        .extracting(SourceRecord::content)
        .containsExactly("  meta before\n", "synthetic failure", "meta after  ");
    assertThat(records.get(1).toolUseId()).contains("synthetic-read");
    assertThat(records.get(1).toolName()).contains("Read");
    assertThat(records.get(1).toolError()).contains("tool_error");
    assertThat(records.get(0).usage().inputTokens()).isEqualTo(17);
    assertThat(records.get(1).usage().inputTokens()).isZero();
    assertThat(records.get(2).usage().inputTokens()).isZero();
    assertThat(records).extracting(SourceRecord::locator).doesNotHaveDuplicates();
  }

  @Test
  void taskTimingPreservesExplicitEpochSecondsDurationAndZero() throws Exception {
    JsonNode event =
        MAPPER.readTree(
            """
            {"type":"event_msg","timestamp":"2026-01-03T12:00:00Z","payload":{"type":"task_complete","turn_id":"synthetic-turn","started_at":1767225600,"completed_at":1767225610,"duration_ms":10500}}
            """);
    var timing =
        JsonSourceRecordMapper.toSourceRecords("synthetic.jsonl", 0, event, "event_msg")
            .getFirst()
            .timing();
    assertThat(timing.kind()).isEqualTo("task_complete");
    assertThat(timing.turnId()).isEqualTo("synthetic-turn");
    assertThat(timing.startedAt()).contains("2026-01-01T00:00:00Z");
    assertThat(timing.completedAt()).contains("2026-01-01T00:00:10Z");
    assertThat(timing.durationMs()).hasValue(10500);
    JsonNode zero =
        MAPPER.readTree(
            """
            {"type":"system","subtype":"turn_duration","durationMs":0,"uuid":"synthetic-zero"}
            """);
    assertThat(
            JsonSourceRecordMapper.toSourceRecords("synthetic.jsonl", 1, zero, "system")
                .getFirst()
                .timing()
                .durationMs())
        .hasValue(0);
  }

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
  @DisplayName("tool_use.input 保留为 JSON 序列化文本")
  void toolUseInputPreservedAsJsonString() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "assistant",
              "message": {
                "id": "msg-1",
                "content": [
                  {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Read",
                    "input": {"file_path": "/synthetic/test.md"}
                  }
                ]
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("test.jsonl", 0, event, "assistant");
    SourceRecord record = records.get(0);

    assertThat(record.toolCalls()).hasSize(1);
    assertThat(record.toolCalls().get(0).toolCallId()).isEqualTo("toolu_1");
    assertThat(record.toolCalls().get(0).name()).isEqualTo("Read");
    assertThat(record.toolCalls().get(0).input()).contains("/synthetic/test.md");
  }

  @Test
  @DisplayName("tool_use 无 input 时 input 为空字符串，空对象 {} 有区别")
  void toolUseMissingInputDiffersFromEmptyObject() throws IOException {
    JsonNode event =
        MAPPER.readTree(
            """
            {
              "type": "assistant",
              "message": {
                "content": [
                  {"type": "tool_use", "id": "t1", "name": "Bash"},
                  {"type": "tool_use", "id": "t2", "name": "Read", "input": {}}
                ]
              }
            }
            """);

    List<SourceRecord> records =
        JsonSourceRecordMapper.toSourceRecords("test.jsonl", 0, event, "assistant");

    assertThat(records.get(0).toolCalls().get(0).input()).isEmpty();
    assertThat(records.get(0).toolCalls().get(1).input()).isEqualTo("{}");
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

  @Test
  @DisplayName("stop_reason 优先从 message.stop_reason 读取，回退到顶层")
  void stopReasonReadsFromMessageFirstThenTopLevel() throws IOException {
    // message.stop_reason 优先
    JsonNode eventWithMessageStop =
        MAPPER.readTree(
            """
            {
              "type": "assistant",
              "stop_reason": "top_level_value",
              "message": {
                "id": "msg-1",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "hello"}]
              }
            }
            """);

    List<SourceRecord> records1 =
        JsonSourceRecordMapper.toSourceRecords("test.jsonl", 0, eventWithMessageStop, "assistant");
    assertThat(records1.get(0).responseStopReason()).contains("end_turn");

    // 无 message.stop_reason 时回退到顶层
    JsonNode eventWithTopLevelOnly =
        MAPPER.readTree(
            """
            {
              "type": "assistant",
              "stop_reason": "tool_use",
              "message": {
                "id": "msg-2",
                "content": [{"type": "text", "text": "hello"}]
              }
            }
            """);

    List<SourceRecord> records2 =
        JsonSourceRecordMapper.toSourceRecords("test.jsonl", 1, eventWithTopLevelOnly, "assistant");
    assertThat(records2.get(0).responseStopReason()).contains("tool_use");
  }
}
