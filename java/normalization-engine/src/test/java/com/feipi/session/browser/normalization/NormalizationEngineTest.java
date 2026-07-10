package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import jakarta.validation.ConstraintViolationException;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link NormalizationEngine} 单元测试。
 *
 * <p>验证归一化引擎在各种输入下的行为，包括空事件、单调用、多调用、 工具执行关联、未知事件诊断和 token 用量提取。
 */
@DisplayName("NormalizationEngine 归一化引擎测试")
class NormalizationEngineTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final NormalizationEngine ENGINE = new NormalizationEngine();

  @Nested
  @DisplayName("空事件")
  class EmptyEventsTests {

    @Test
    @DisplayName("空事件列表返回正确的空制品")
    void emptyEventsReturnsCorrectEmptyArtifact() {
      NormalizedSessionArtifact artifact =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());

      assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
      assertThat(artifact.agent()).isEqualTo(NormalizedAgent.CLAUDE_CODE);
      assertThat(artifact.calls()).isEmpty();
      assertThat(artifact.toolExecutions()).isEmpty();
      assertThat(artifact.sourceFiles()).isEmpty();
      assertThat(artifact.diagnostics()).isEmpty();
    }
  }

  @Nested
  @DisplayName("单个调用")
  class SingleCallTests {

    @Test
    @DisplayName("单个 assistant 消息产生单个调用")
    void singleAssistantMessageProducesSingleCall() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "call-1");
      event.put("model", "claude-3-sonnet");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, TestSourceRecords.records(event), List.of(), List.of());

      assertThat(artifact.calls()).hasSize(1);
      assertThat(artifact.calls().get(0).callId()).isEqualTo("call-1");
      assertThat(artifact.calls().get(0).callIndex()).isEqualTo(1);
      assertThat(artifact.calls().get(0).callKey()).isEqualTo("C1");
      assertThat(artifact.calls().get(0).model()).isEqualTo("claude-3-sonnet");
    }
  }

  @Nested
  @DisplayName("工具执行关联")
  class ToolExecutionTests {

    @Test
    @DisplayName("tool_use + tool_result 正确关联")
    void toolUseAndToolResultCorrectlyLinked() {
      // 构建事件流：assistant(C1, tool_use:Read) -> tool_result -> assistant(C2)
      ObjectNode assistant1 = MAPPER.createObjectNode();
      assistant1.put("type", "assistant");
      assistant1.put("id", "C1");
      assistant1.put("model", "claude-3-sonnet");
      ArrayNode content = assistant1.putArray("content");
      ObjectNode toolUse = content.addObject();
      toolUse.put("type", "tool_use");
      toolUse.put("id", "toolu_1");
      toolUse.put("name", "Read");

      ObjectNode toolResult = MAPPER.createObjectNode();
      toolResult.put("type", "tool_result");
      toolResult.put("tool_use_id", "toolu_1");

      ObjectNode assistant2 = MAPPER.createObjectNode();
      assistant2.put("type", "assistant");
      assistant2.put("id", "C2");
      assistant2.put("model", "claude-3-sonnet");

      List<JsonNode> events = List.of(assistant1, toolResult, assistant2);
      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, TestSourceRecords.records(events), List.of(), List.of());

      assertThat(artifact.toolExecutions()).hasSize(1);
      assertThat(artifact.toolExecutions().get(0).toolCallId()).isEqualTo("toolu_1");
      assertThat(artifact.toolExecutions().get(0).name()).isEqualTo("Read");
      assertThat(artifact.toolExecutions().get(0).declaredByCallId()).isEqualTo("C1");
      assertThat(artifact.toolExecutions().get(0).resultConsumedByCallId()).hasValue("C2");
    }
  }

  @Nested
  @DisplayName("未知事件诊断")
  class UnknownEventTests {

    @Test
    @DisplayName("未知事件类型产生诊断信息")
    void unknownEventTypeProducesDiagnostic() {
      ObjectNode unknown = MAPPER.createObjectNode();
      unknown.put("type", "custom_event");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(unknown),
              List.of(),
              List.of());

      assertThat(artifact.diagnostics()).hasSize(1);
      assertThat(artifact.diagnostics().get(0).get("message")).asString().contains("custom_event");
      assertThat(artifact.diagnostics().get(0).get("severity")).isEqualTo("WARNING");
    }

    @Test
    @DisplayName("未知事件诊断与输入诊断合并")
    void unknownEventDiagnosticsMergeWithInputDiagnostics() {
      ObjectNode unknown = MAPPER.createObjectNode();
      unknown.put("type", "weird_event");

      SourceDiagnostic inputDiag =
          new SourceDiagnostic(
              ParseSeverity.ERROR,
              ParseIssueType.BAD_JSON,
              "bad json line",
              5,
              Optional.empty(),
              ParseIssueType.BAD_JSON.name(),
              "",
              OptionalInt.empty(),
              OptionalInt.empty(),
              OptionalInt.empty());

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(unknown),
              List.of(inputDiag),
              List.of());

      assertThat(artifact.diagnostics()).hasSize(2);
    }
  }

  @Nested
  @DisplayName("Token 用量")
  class TokenUsageTests {

    @Test
    @DisplayName("token 用量从事件中正确提取")
    void tokenUsageExtractedFromEvents() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "call-1");
      ObjectNode usage = event.putObject("usage");
      usage.put("input_tokens", 100);
      usage.put("output_tokens", 200);
      usage.put("cache_read_input_tokens", 50);
      usage.put("cache_creation_input_tokens", 10);

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, TestSourceRecords.records(event), List.of(), List.of());

      assertThat(artifact.calls()).hasSize(1);
      assertThat(artifact.calls().get(0).usage().fresh()).isEqualTo(100);
      assertThat(artifact.calls().get(0).usage().output()).isEqualTo(200);
      assertThat(artifact.calls().get(0).usage().cacheRead()).isEqualTo(50);
      assertThat(artifact.calls().get(0).usage().cacheWrite()).isEqualTo(10);
      assertThat(artifact.calls().get(0).usage().total()).isEqualTo(360);
    }

    @Test
    @DisplayName("无 usage 字段时 token 用量为零")
    void noUsageFieldResultsInZeroUsage() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "call-1");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, TestSourceRecords.records(event), List.of(), List.of());

      assertThat(artifact.calls().get(0).usage().total()).isZero();
      assertThat(artifact.calls().get(0).usage().fresh()).isZero();
      assertThat(artifact.calls().get(0).usage().output()).isZero();
    }
  }

  @Nested
  @DisplayName("Agent 验证")
  class AgentValidationTests {

    @Test
    @DisplayName("非法 agent 值抛出异常")
    void invalidAgentThrowsException() {
      assertThatThrownBy(() -> NormalizedAgent.fromValue("invalid_agent"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("invalid normalized agent");
    }

    @Test
    @DisplayName("所有合法 agent 值均可使用")
    void allValidAgentValuesWork() {
      for (NormalizedAgent agent : NormalizedAgent.values()) {
        NormalizedSessionArtifact artifact =
            ENGINE.normalize(agent, List.of(), List.of(), List.of());
        assertThat(artifact.agent()).isEqualTo(agent);
      }
    }
  }

  @Nested
  @DisplayName("确定性")
  class DeterminismTests {

    @Test
    @DisplayName("相同输入产生相同输出")
    void sameInputProducesSameOutput() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "call-1");
      event.put("model", "claude-3-sonnet");

      NormalizedSessionArtifact artifact1 =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, TestSourceRecords.records(event), List.of(), List.of());
      NormalizedSessionArtifact artifact2 =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, TestSourceRecords.records(event), List.of(), List.of());

      assertThat(artifact1).isEqualTo(artifact2);
    }
  }

  @Nested
  @DisplayName("Schema 版本")
  class SchemaVersionTests {

    @Test
    @DisplayName("制品 schema 版本来自 NormalizedConstants")
    void artifactSchemaVersionFromConstants() {
      NormalizedSessionArtifact artifact =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());

      assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    }
  }

  @Nested
  @DisplayName("源文件")
  class SourceFileTests {

    @Test
    @DisplayName("源文件正确传递到制品")
    void sourceFilesPassedThroughToArtifact() {
      NormalizedSourceFile file =
          new NormalizedSourceFile(
              SourceFileRole.TRANSCRIPT,
              Path.of("/path/to/session.jsonl"),
              Optional.empty(),
              Optional.empty());

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of(file));

      assertThat(artifact.sourceFiles()).hasSize(1);
      assertThat(artifact.sourceFiles().get(0).path()).isEqualTo(Path.of("/path/to/session.jsonl"));
    }
  }

  @Nested
  @DisplayName("Session 元数据")
  class SessionMetaTests {

    @Test
    @DisplayName("空事件的 session 包含基本字段")
    void emptyEventsSessionContainsBasicFields() {
      NormalizedSessionArtifact artifact =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());

      assertThat(artifact.session()).containsEntry("agent", "claude_code");
      assertThat(artifact.session()).containsEntry("eventCount", 0);
      assertThat(artifact.session()).containsEntry("totalTokens", 0L);
    }

    @Test
    @DisplayName("session eventCount 匹配事件数")
    void sessionEventCountMatchesEvents() {
      ObjectNode event1 = MAPPER.createObjectNode().put("type", "assistant").put("id", "c1");
      ObjectNode event2 = MAPPER.createObjectNode().put("type", "user");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CODEX,
              TestSourceRecords.records(event1, event2),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("eventCount", 2);
    }

    @Test
    @DisplayName("session totalTokens 等于调用 token 总和")
    void sessionTotalTokensEqualsCallSum() {
      ObjectNode event1 = MAPPER.createObjectNode().put("type", "assistant").put("id", "c1");
      event1.putObject("usage").put("input_tokens", 100).put("output_tokens", 200);
      ObjectNode event2 = MAPPER.createObjectNode().put("type", "assistant").put("id", "c2");
      event2.putObject("usage").put("input_tokens", 50).put("output_tokens", 150);

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(event1, event2),
              List.of(),
              List.of());

      // 第一个调用 token 总和为 300，第二个为 200，合计 500
      assertThat(artifact.session()).containsEntry("totalTokens", 500L);
    }

    @Test
    @DisplayName("session 包含工具守恒计数")
    void sessionContainsConservationCounts() {
      ObjectNode assistant = MAPPER.createObjectNode();
      assistant.put("type", "assistant");
      assistant.put("id", "C1");
      ArrayNode content = assistant.putArray("content");
      ObjectNode toolUse = content.addObject();
      toolUse.put("type", "tool_use");
      toolUse.put("id", "toolu_1");
      toolUse.put("name", "Read");

      ObjectNode toolResult = MAPPER.createObjectNode();
      toolResult.put("type", "tool_result");
      toolResult.put("tool_use_id", "toolu_1");

      ObjectNode assistant2 = MAPPER.createObjectNode();
      assistant2.put("type", "assistant");
      assistant2.put("id", "C2");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(assistant, toolResult, assistant2),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("declaredTools", 1);
      assertThat(artifact.session()).containsEntry("executedTools", 1);
      assertThat(artifact.session()).containsEntry("consumedResults", 1);
    }
  }

  @Nested
  @DisplayName("源单元目录")
  class SourceUnitCatalogTests {

    @Test
    @DisplayName("无源文件时目录为空")
    void emptySourceFilesProducesEmptyCatalog() {
      NormalizedSessionArtifact artifact =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());

      assertThat(artifact.sourceUnitCatalog()).isEmpty();
    }

    @Test
    @DisplayName("源文件对应目录条目")
    void sourceFilesProduceCatalogEntries() {
      NormalizedSourceFile file =
          new NormalizedSourceFile(
              SourceFileRole.TRANSCRIPT,
              Path.of("/path/to/session.jsonl"),
              Optional.empty(),
              Optional.empty());

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of(file));

      assertThat(artifact.sourceUnitCatalog()).hasSize(1);
      assertThat(artifact.sourceUnitCatalog()).containsKey("/path/to/session.jsonl");
      SourceUnitCatalogEntry entry = artifact.sourceUnitCatalog().get("/path/to/session.jsonl");
      assertThat(entry.unitKey()).isEqualTo("/path/to/session.jsonl");
      assertThat(entry.originPath()).isEqualTo("/path/to/session.jsonl");
      assertThat(entry.unitType()).isEqualTo("transcript");
      assertThat(entry.direction()).isEqualTo(SourceUnitDirection.REQUEST);
    }

    @Test
    @DisplayName("多个源文件产生多个目录条目")
    void multipleSourceFilesProduceMultipleEntries() {
      NormalizedSourceFile file1 =
          new NormalizedSourceFile(
              SourceFileRole.TRANSCRIPT,
              Path.of("/path/a.jsonl"),
              Optional.empty(),
              Optional.empty());
      NormalizedSourceFile file2 =
          new NormalizedSourceFile(
              SourceFileRole.COMPANION,
              Path.of("/path/b.jsonl"),
              Optional.empty(),
              Optional.empty());

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of(file1, file2));

      assertThat(artifact.sourceUnitCatalog()).hasSize(2);
      assertThat(artifact.sourceUnitCatalog()).containsKey("/path/a.jsonl");
      assertThat(artifact.sourceUnitCatalog()).containsKey("/path/b.jsonl");
    }
  }

  @Nested
  @DisplayName("Codex 语义计数")
  class CodexCountingTests {

    @Test
    @DisplayName("CODEX agent 使用 turnId 编码的子类型精确统计 user/assistant/tool")
    void codexAgentUsesTurnIdSubtypeCounting() {
      // 用户消息事件，计入用户计数
      ObjectNode userMsg =
          MAPPER.createObjectNode().put("type", "event_msg").put("turnId", "user_message");
      // 助手消息事件，不计入用户计数
      ObjectNode agentMsg =
          MAPPER.createObjectNode().put("type", "event_msg").put("turnId", "agent_message");
      // 新 schema 令牌用量记录可在有时间阈值时计入助手计数；本用例仍由旧 schema agent_message 计入助手计数
      ObjectNode assistant = MAPPER.createObjectNode().put("type", "assistant").put("id", "tc:0");
      // 函数调用工具，计入工具计数
      ObjectNode funcCall =
          MAPPER
              .createObjectNode()
              .put("type", "tool_use")
              .put("turnId", "function_call")
              .put("name", "shell");
      // 自定义工具调用，计入工具计数
      ObjectNode customCall =
          MAPPER
              .createObjectNode()
              .put("type", "tool_use")
              .put("turnId", "custom_tool_call")
              .put("name", "custom");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CODEX,
              TestSourceRecords.records(userMsg, agentMsg, assistant, funcCall, customCall),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("userMessageCount", 1L);
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
      assertThat(artifact.session()).containsEntry("toolCallCount", 2L);
    }

    @Test
    @DisplayName("Codex 运行索引兼容：边界前结束的 token_count 会话仍按 agent_message 计数")
    void codexLegacyRuntimeIndexUsesAgentMessageBeforeCutoff() {
      ObjectNode agentMsg =
          MAPPER
              .createObjectNode()
              .put("type", "event_msg")
              .put("turnId", "agent_message")
              .put("timestamp", "2026-06-20T02:14:00Z");
      ObjectNode tokenCount1 =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "token_count:1")
              .put("timestamp", "2026-06-20T02:15:00Z");
      ObjectNode tokenCount2 =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "token_count:2")
              .put("timestamp", "2026-06-20T02:16:00Z");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CODEX,
              TestSourceRecords.records(agentMsg, tokenCount1, tokenCount2),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
    }

    @Test
    @DisplayName("Codex 运行索引兼容：跨过边界的 token_count 会话按 LLM call 计数")
    void codexPostRolloutRuntimeIndexUsesTokenCountAfterCutoff() {
      ObjectNode agentMsg =
          MAPPER
              .createObjectNode()
              .put("type", "event_msg")
              .put("turnId", "agent_message")
              .put("timestamp", "2026-06-20T02:14:00Z");
      ObjectNode tokenCount1 =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "token_count:1")
              .put("timestamp", "2026-06-20T02:15:00Z");
      ObjectNode tokenCount2 =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "token_count:2")
              .put("timestamp", "2026-06-20T16:00:00Z");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CODEX,
              TestSourceRecords.records(agentMsg, tokenCount1, tokenCount2),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("assistantMessageCount", 2L);
    }

    @Test
    @DisplayName("非 CODEX agent 使用通用分类计数")
    void nonCodexAgentUsesGenericCounting() {
      ObjectNode user = MAPPER.createObjectNode().put("type", "user");
      ObjectNode assistant = MAPPER.createObjectNode().put("type", "assistant").put("id", "c1");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(user, assistant),
              List.of(),
              List.of());

      // 通用计数：显式写入 dashboard 所需 user/assistant/tool 汇总键
      assertThat(artifact.session()).containsEntry("userMessageCount", 1L);
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
      assertThat(artifact.session()).containsEntry("toolCallCount", 0L);
    }
  }

  @Nested
  @DisplayName("Claude 语义计数")
  class ClaudeCountingTests {

    @Test
    @DisplayName("CLAUDE_CODE 排除带 toolUseId 的 user 事件（实际为 tool_result）")
    void claudeCodeExcludesToolResultUserEvents() {
      // 真实用户消息
      ObjectNode userMsg = MAPPER.createObjectNode().put("type", "user");
      // 伪装为 user 的 tool_result（携带 tool_use_id）
      ObjectNode toolResultAsUser =
          MAPPER.createObjectNode().put("type", "user").put("tool_use_id", "toolu_1");
      // 助手消息
      ObjectNode assistant = MAPPER.createObjectNode().put("type", "assistant").put("id", "c1");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(userMsg, toolResultAsUser, assistant),
              List.of(),
              List.of());

      // 只有真实用户消息被计数，带 tool_use_id 的被排除
      assertThat(artifact.session()).containsEntry("userMessageCount", 1L);
    }

    @Test
    @DisplayName("CLAUDE_CODE 纯 user 事件全部计数")
    void claudeCodeCountsAllPureUserEvents() {
      ObjectNode user1 = MAPPER.createObjectNode().put("type", "user");
      ObjectNode user2 = MAPPER.createObjectNode().put("type", "user");
      ObjectNode assistant = MAPPER.createObjectNode().put("type", "assistant").put("id", "c1");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(user1, user2, assistant),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("userMessageCount", 2L);
    }

    @Test
    @DisplayName("CLAUDE_CODE Dashboard 消息计数排除物化 subagent sidecar")
    void claudeCodeDashboardMessageCountsExcludeMaterializedSubagentSidecars() {
      ObjectNode user = MAPPER.createObjectNode().put("type", "user");

      ObjectNode mainAssistant =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "main-call")
              .put("turnId", "main-turn");
      mainAssistant.putObject("usage").put("input_tokens", 10).put("output_tokens", 1);
      ArrayNode mainContent = mainAssistant.putArray("content");
      ObjectNode mainToolUse = mainContent.addObject();
      mainToolUse.put("type", "tool_use");
      mainToolUse.put("id", "toolu_main");
      mainToolUse.put("name", "Task");

      ObjectNode subagentUser =
          MAPPER
              .createObjectNode()
              .put("type", "user")
              .put("locator", "sessions/main/subagents/agent-worker.jsonl#event[0]");

      ObjectNode subagentAssistant =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "subagent-call")
              .put("turnId", "subagent-turn")
              .put("locator", "sessions/main/subagents/agent-worker.jsonl#event[1]");
      subagentAssistant.putObject("usage").put("input_tokens", 20).put("output_tokens", 2);
      ArrayNode subagentContent = subagentAssistant.putArray("content");
      ObjectNode subagentToolUse = subagentContent.addObject();
      subagentToolUse.put("type", "tool_use");
      subagentToolUse.put("id", "toolu_subagent");
      subagentToolUse.put("name", "Read");

      ObjectNode subagentToolResult =
          MAPPER
              .createObjectNode()
              .put("type", "tool_result")
              .put("tool_use_id", "toolu_subagent")
              .put("is_error", "true")
              .put("locator", "sessions/main/subagents/agent-worker.jsonl#event[2]");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(
                  user, mainAssistant, subagentUser, subagentAssistant, subagentToolResult),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("userMessageCount", 1L);
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
      assertThat(artifact.session()).containsEntry("toolCallCount", 2L);
      assertThat(artifact.session()).containsEntry("failedToolCount", 1L);
      assertThat(artifact.session()).containsEntry("totalTokens", 33L);
    }

    @Test
    @DisplayName("CLAUDE_CODE ended_at 使用全量事件最大时间而非追加的 subagent call 顺序")
    void claudeCodeTimestampRangeUsesRecordMaxInsteadOfAppendedSubagentCallOrder() {
      ObjectNode user =
          MAPPER
              .createObjectNode()
              .put("type", "user")
              .put("timestamp", "2026-06-21T15:38:40.332Z");

      ObjectNode mainAssistant =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "main-call")
              .put("turnId", "main-turn")
              .put("timestamp", "2026-06-22T00:32:18.535Z");

      ObjectNode finalSystemEvent =
          MAPPER
              .createObjectNode()
              .put("type", "system")
              .put("timestamp", "2026-06-22T00:35:45.454Z");

      ObjectNode appendedSubagentAssistant =
          MAPPER
              .createObjectNode()
              .put("type", "assistant")
              .put("id", "subagent-call")
              .put("turnId", "subagent-turn")
              .put("timestamp", "2026-06-21T17:07:02.663Z")
              .put("locator", "sessions/main/subagents/agent-worker.jsonl#event[1]");

      NormalizedSessionArtifact artifact =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE,
              TestSourceRecords.records(
                  user, mainAssistant, finalSystemEvent, appendedSubagentAssistant),
              List.of(),
              List.of());

      assertThat(artifact.session()).containsEntry("started_at", "2026-06-21T15:38:40.332Z");
      assertThat(artifact.session()).containsEntry("ended_at", "2026-06-22T00:35:45.454Z");
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
    }
  }

  @Nested
  @DisplayName("守恒检查")
  class ConservationTests {

    @Test
    @DisplayName("守恒检查结果记录正确")
    void conservationCheckResultRecordsCorrectly() {
      NormalizationEngine.ConservationCheckResult result =
          new NormalizationEngine.ConservationCheckResult(3, 3, 2, true);

      assertThat(result.declaredTools()).isEqualTo(3);
      assertThat(result.executedTools()).isEqualTo(3);
      assertThat(result.consumedResults()).isEqualTo(2);
      assertThat(result.tokensConserved()).isTrue();
    }

    @Test
    @DisplayName("空调用的守恒检查结果为零")
    void emptyCallsProduceZeroConservation() {
      NormalizationEngine.ConservationCheckResult result =
          NormalizationEngine.buildConservationCheck(List.of(), List.of());

      assertThat(result.declaredTools()).isZero();
      assertThat(result.executedTools()).isZero();
      assertThat(result.consumedResults()).isZero();
      assertThat(result.tokensConserved()).isTrue();
    }

    @Test
    @DisplayName("守恒检查 token 始终守恒")
    void conservationCheckTokenAlwaysConserved() {
      ObjectNode event = MAPPER.createObjectNode();
      event.put("type", "assistant");
      event.put("id", "c1");
      event.putObject("usage").put("input_tokens", 100).put("output_tokens", 200);

      EventClassifier.ClassifiedEvents classified =
          EventClassifier.classify(TestSourceRecords.records(event));
      List<com.feipi.session.browser.domain.normalized.NormalizedCall> calls =
          CallBuilder.buildCalls(TestSourceRecords.records(event), classified);

      NormalizationEngine.ConservationCheckResult result =
          NormalizationEngine.buildConservationCheck(calls, List.of());

      assertThat(result.tokensConserved()).isTrue();
    }

    @Test
    @DisplayName("守恒检查负数参数被拒绝")
    void conservationCheckRejectsNegativeValues() {
      assertThatThrownBy(() -> new NormalizationEngine.ConservationCheckResult(-1, 0, 0, true))
          .isInstanceOf(ConstraintViolationException.class);
      assertThatThrownBy(() -> new NormalizationEngine.ConservationCheckResult(0, -1, 0, true))
          .isInstanceOf(ConstraintViolationException.class);
      assertThatThrownBy(() -> new NormalizationEngine.ConservationCheckResult(0, 0, -1, true))
          .isInstanceOf(ConstraintViolationException.class);
    }
  }
}
