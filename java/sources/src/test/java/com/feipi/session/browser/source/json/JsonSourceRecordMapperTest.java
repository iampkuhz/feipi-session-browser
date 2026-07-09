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

    SourceRecord record = JsonSourceRecordMapper.toSourceRecord("session.jsonl", 4, event, "user");

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

    SourceRecord record = JsonSourceRecordMapper.toSourceRecord("session.jsonl", 5, event, "user");

    assertThat(record.eventType()).isEqualTo("user");
    assertThat(record.toolUseId()).isEmpty();
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

    SourceRecord record =
        JsonSourceRecordMapper.toSourceRecord("session.jsonl", 6, event, "assistant");

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
}
