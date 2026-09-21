package com.feipi.session.browser.contracttest.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.json.JsonSourceRecordMapper;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Qoder 响应语义契约测试。
 *
 * <p>证明从 JsonSourceRecordMapper → NormalizationEngine → SessionDetailAssembler.buildRounds
 * 的完整链路中，两次逻辑 response（首次 text+2 Read 分片，第二次消费 2 结果后 end text）产生 2 个逻辑 call、2 个 round、2
 * 个工具执行，且工具参数在 artifact 中保留。
 */
@DisplayName("Qoder 响应语义契约测试")
class QoderResponseSemanticsContractTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final NormalizationEngine ENGINE = new NormalizationEngine();

  private static final String[] SYNTHETIC_EVENTS = {
    """
    {"type":"user","uuid":"u1","message":{"role":"user","content":"Inspect synthetic files"}}\
    """,
    """
    {"type":"assistant","uuid":"a1-text","message":{"id":"message-one","role":"assistant","model":"synthetic-model","content":[{"type":"text","text":"I will inspect two files."}]}}\
    """,
    """
    {"type":"assistant","uuid":"a1-read1","message":{"id":"message-one","role":"assistant","model":"synthetic-model","content":[{"type":"tool_use","id":"read-one","name":"Read","input":{"file_path":"/synthetic/first.md"}}]}}\
    """,
    """
    {"type":"assistant","uuid":"a1-read2","message":{"id":"message-one","role":"assistant","model":"synthetic-model","stop_reason":"tool_use","content":[{"type":"tool_use","id":"read-two","name":"Read","input":{"file_path":"/synthetic/second.md"}}]}}\
    """,
    """
    {"type":"user","uuid":"results","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"read-one","content":"First synthetic result"},{"type":"tool_result","tool_use_id":"read-two","content":"Second synthetic result"}]}}\
    """,
    """
    {"type":"assistant","uuid":"a2","message":{"id":"message-two","role":"assistant","model":"synthetic-model","stop_reason":"end_turn","content":[{"type":"text","text":"Both files inspected."}]}}\
    """
  };

  @Test
  @DisplayName("两次逻辑 response 归一化为 2 个 call，不是 4 个")
  void twoLogicalResponsesProduceTwoCalls() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    assertThat(artifact.calls()).hasSize(2);
  }

  @Test
  @DisplayName("buildRounds 产生 2 个 round")
  void buildRoundsProducesTwoRounds() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();
    var rounds = SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions());

    assertThat(rounds).hasSize(2);
  }

  @Test
  @DisplayName("工具执行数 = 2（Read × 2），不多不少")
  void toolExecutionCountIsTwo() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    assertThat(artifact.toolExecutions()).hasSize(2);
    assertThat(artifact.toolExecutions())
        .extracting(NormalizedToolExecution::name)
        .containsExactly("Read", "Read");
    assertThat(artifact.toolExecutions())
        .extracting(NormalizedToolExecution::toolCallId)
        .containsExactly("read-one", "read-two");
  }

  @Test
  @DisplayName("第一个 call 声明 2 个工具，消费 0 个结果")
  void firstCallDeclaresTwoToolsConsumesNone() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    NormalizedCall first = artifact.calls().get(0);
    assertThat(first.response().toolCallIds()).containsExactly("read-one", "read-two");
    assertThat(first.request().toolResultIds()).isEmpty();
  }

  @Test
  @DisplayName("第二个 call 消费 2 个 tool result")
  void secondCallConsumesTwoResults() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    NormalizedCall second = artifact.calls().get(1);
    assertThat(second.request().toolResultIds()).containsExactly("read-one", "read-two");
    assertThat(second.response().toolCallIds()).isEmpty();
  }

  @Test
  @DisplayName("工具参数在 sourceUnits 中保留")
  void toolInputPreservedInSourceUnits() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    NormalizedCall first = artifact.calls().get(0);
    List<Map<String, Object>> sourceUnits = first.sourceUnits();

    List<Map<String, Object>> toolUseUnits =
        sourceUnits.stream().filter(u -> "tool_use".equals(u.get("type"))).toList();

    assertThat(toolUseUnits).hasSize(2);

    Map<String, Object> readOne =
        toolUseUnits.stream().filter(u -> "read-one".equals(u.get("id"))).findFirst().orElseThrow();
    assertThat(readOne).containsEntry("name", "Read");
    assertThat(readOne).containsEntry("role", "assistant");
    assertThat(readOne.get("input").toString()).contains("/synthetic/first.md");

    Map<String, Object> readTwo =
        toolUseUnits.stream().filter(u -> "read-two".equals(u.get("id"))).findFirst().orElseThrow();
    assertThat(readTwo.get("input").toString()).contains("/synthetic/second.md");
  }

  @Test
  @DisplayName("assistant 文本与工具声明在 sourceUnits 中分离")
  void assistantTextAndToolDeclarationsAreSeparate() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    NormalizedCall first = artifact.calls().get(0);
    List<Map<String, Object>> sourceUnits = first.sourceUnits();

    List<Map<String, Object>> assistantTextUnits =
        sourceUnits.stream()
            .filter(u -> "assistant".equals(u.get("type")) && "assistant".equals(u.get("role")))
            .toList();
    assertThat(assistantTextUnits).hasSize(1);
    assertThat(assistantTextUnits.get(0).get("text").toString())
        .contains("I will inspect two files.");

    List<Map<String, Object>> toolUseUnits =
        sourceUnits.stream().filter(u -> "tool_use".equals(u.get("type"))).toList();
    assertThat(toolUseUnits).hasSize(2);
  }

  @Test
  @DisplayName("第二个 call 的 tool_result 正确关联")
  void secondCallToolResultsCorrectlyAssociated() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    NormalizedCall second = artifact.calls().get(1);
    List<Map<String, Object>> sourceUnits = second.sourceUnits();

    List<Map<String, Object>> toolResultUnits =
        sourceUnits.stream().filter(u -> "tool_result".equals(u.get("type"))).toList();
    assertThat(toolResultUnits).hasSize(2);
    assertThat(toolResultUnits)
        .extracting(u -> u.get("tool_call_id"))
        .containsExactly("read-one", "read-two");
  }

  @Test
  @DisplayName("工具执行声明归属正确")
  void toolExecutionDeclarationOwnership() {
    NormalizedSessionArtifact artifact = normalizeSynthetic();

    for (NormalizedToolExecution exec : artifact.toolExecutions()) {
      assertThat(exec.declaredByCallId()).isEqualTo(artifact.calls().get(0).callId());
    }
    assertThat(artifact.toolExecutions().get(0).resultConsumedByCallId())
        .hasValue(artifact.calls().get(1).callId());
    assertThat(artifact.toolExecutions().get(1).resultConsumedByCallId())
        .hasValue(artifact.calls().get(1).callId());
  }

  @Test
  @DisplayName("重复 tool id 不重复计数")
  void duplicateToolIdsNotDoubleCounted() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[\
      {"type":"tool_use","id":"dup-1","name":"Read","input":{"file_path":"/a"}}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[\
      {"type":"tool_use","id":"dup-1","name":"Read","input":{"file_path":"/stale"}}]}}\
      """,
      """
      {"type":"user","message":{"content":[\
      {"type":"tool_result","tool_use_id":"dup-1","content":"ok"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m2","content":[{"type":"text","text":"done"}]}}\
      """
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);

    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.toolExecutions()).hasSize(1);
    assertThat(artifact.toolExecutions().get(0).toolCallId()).isEqualTo("dup-1");
    assertThat(artifact.toolExecutions().get(0).name()).isEqualTo("Read");
  }

  @Test
  @DisplayName("不同 message.id 的响应不合并")
  void differentMessageIdsProduceSeparateCalls() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"part1"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m2","content":[{"type":"text","text":"part2"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);

    assertThat(artifact.calls()).hasSize(2);
  }

  @Test
  @DisplayName("Claude/Codex 回归：非 Qoder agent 不受合并影响")
  void nonQoderAgentsUnaffected() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","id":"c1","message":{"id":"m1","content":[{"type":"text","text":"part1"}]}}\
      """,
      """
      {"type":"assistant","id":"c2","message":{"id":"m1","content":[{"type":"text","text":"part2"}]}}\
      """,
    };

    for (NormalizedAgent agent : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.CODEX)) {
      NormalizedSessionArtifact artifact = normalizeEventsAs(events, agent);
      assertThat(artifact.calls()).as("agent=%s should not merge", agent).hasSize(2);
    }
  }

  @Test
  @DisplayName("多 scope/subagent 不影响合并")
  void multipleScopesDoNotInterfere() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"main1"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[\
      {"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"/x"}}]}}\
      """,
      """
      {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"ok"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m2","content":[{"type":"text","text":"done"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);
    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.toolExecutions()).hasSize(1);
  }

  @Test
  @DisplayName("空输入参数与缺失有区别")
  void emptyInputDiffersFromMissing() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[\
      {"type":"tool_use","id":"t1","name":"Read","input":{}}]}}\
      """,
      """
      {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"ok"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m2","content":[\
      {"type":"tool_use","id":"t2","name":"Bash"}]}}\
      """,
      """
      {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","content":"ok"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m3","content":[{"type":"text","text":"done"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);

    assertThat(artifact.calls()).hasSize(3);

    // 首次调用的工具输入是显式空对象，与输入缺失不同。
    NormalizedCall first = artifact.calls().get(0);
    List<Map<String, Object>> firstToolUseUnits =
        first.sourceUnits().stream().filter(u -> "tool_use".equals(u.get("type"))).toList();
    assertThat(firstToolUseUnits).hasSize(1);
    assertThat(firstToolUseUnits.get(0).get("input").toString()).isEqualTo("{}");

    // 第二次调用的工具未记录输入，保留缺失状态。
    NormalizedCall second = artifact.calls().get(1);
    List<Map<String, Object>> secondToolUseUnits =
        second.sourceUnits().stream().filter(u -> "tool_use".equals(u.get("type"))).toList();
    assertThat(secondToolUseUnits).hasSize(1);
    assertThat(secondToolUseUnits.get(0).get("input").toString()).isEmpty();
  }

  @Test
  @DisplayName("零用量场景正常处理")
  void zeroUsageHandled() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"ok"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);

    assertThat(artifact.calls()).hasSize(1);
    assertThat(artifact.calls().get(0).usage().total()).isZero();
  }

  @Test
  @DisplayName("首片 usage 全 0、末片非零：合并后保留末片非零值")
  void firstZeroUsageLastNonZeroKeepsLastNonZero() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"part1"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","usage":{"input_tokens":100,"output_tokens":200},"content":[{"type":"text","text":"part2"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);

    assertThat(artifact.calls()).hasSize(1);
    assertThat(artifact.calls().get(0).usage().fresh()).isEqualTo(100);
    assertThat(artifact.calls().get(0).usage().output()).isEqualTo(200);
  }

  @Test
  @DisplayName("首片 input 空、后续完整：合并后保留完整参数")
  void firstEmptyInputLaterCompleteKeepsComplete() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[\
      {"type":"tool_use","id":"t1","name":"Read"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[\
      {"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"/complete.md"}}]}}\
      """,
      """
      {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"ok"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m2","content":[{"type":"text","text":"done"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);

    assertThat(artifact.calls()).hasSize(2);
    NormalizedCall first = artifact.calls().get(0);
    List<Map<String, Object>> toolUseUnits =
        first.sourceUnits().stream().filter(u -> "tool_use".equals(u.get("type"))).toList();
    assertThat(toolUseUnits).hasSize(1);
    assertThat(toolUseUnits.get(0).get("input").toString()).contains("/complete.md");
  }

  @Test
  @DisplayName("空对象工具声明后收到完整参数时保留完整输入")
  void emptyObjectInputUpgradedByCompleteFragment() {
    String[] events = {
      """
      {"type":"assistant","message":{"id":"m1","content":[
      {"type":"tool_use","id":"t1","name":"Read","input":{}}]}}
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":[
      {"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"/synthetic/complete.md"}}]}}
      """
    };
    var artifact = normalizeEvents(events);
    assertThat(artifact.calls()).hasSize(1);
    assertThat(artifact.toolExecutions()).hasSize(1);
    assertThat(
            artifact.calls().get(0).sourceUnits().stream()
                .filter(unit -> "tool_use".equals(unit.get("type")))
                .toList())
        .singleElement()
        .satisfies(
            unit -> assertThat(unit.get("input").toString()).contains("/synthetic/complete.md"));
  }

  @Test
  @DisplayName("同 message.id 终止后重用：产生 2 个 call 和 2 个 round")
  void sameMessageIdReusedAfterStopProducesTwoRounds() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","stop_reason":"tool_use","content":[\
      {"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"/a"}}]}}\
      """,
      """
      {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"ok"}]}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","stop_reason":"end_turn","content":[{"type":"text","text":"done"}]}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);
    var rounds = SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions());

    assertThat(artifact.calls()).hasSize(2);
    assertThat(rounds).hasSize(2);
    assertThat(artifact.calls().get(0).turnId()).isNotEqualTo(artifact.calls().get(1).turnId());
  }

  @Test
  @DisplayName("不同 subagentId 的同 message.id 不合并")
  void differentSubagentIdsDoNotMerge() {
    // 构造两条 assistant 记录，responseMessageId 相同但 relation.subagentId 不同
    var mainRecord =
        new SourceRecord(
            "main#event[0]",
            0,
            "assistant",
            Optional.of("c1"),
            Optional.empty(),
            Optional.empty(),
            Optional.of("m1"),
            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
            "main text",
            Optional.of("m1"),
            Optional.empty());

    var subRelation =
        new com.feipi.session.browser.domain.source.SourceRecordRelation(
            Optional.of("sub-1"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    var subRecord =
        new SourceRecord(
            "sub#event[0]",
            0,
            "assistant",
            Optional.of("c2"),
            Optional.empty(),
            Optional.empty(),
            Optional.of("m1"),
            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            subRelation,
            "sub text",
            Optional.of("m1"),
            Optional.empty());

    var artifact =
        ENGINE.normalize(
            NormalizedAgent.QODER, List.of(mainRecord, subRecord), List.of(), List.of());

    assertThat(artifact.calls()).hasSize(2);
  }

  @Test
  @DisplayName(
      "边界：nested stop 无中断——相邻同 message.id，首片 terminal，无 user/tool_result 中断→2 calls/2 rounds")
  void nestedStopWithoutInterruptProducesTwoCallsAndRounds() {
    String[] events = {
      """
      {"type":"assistant","message":{"id":"m1","stop_reason":"end_turn","content":"one"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":"two"}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);
    var rounds = SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions());

    assertThat(artifact.calls()).hasSize(2);
    assertThat(rounds).hasSize(2);
    assertThat(artifact.calls().get(0).callId()).isNotEqualTo(artifact.calls().get(1).callId());
  }

  @Test
  @DisplayName("边界：sharedparent 无显式 ID——同 parentUuid 无 message.id→2 calls/2 rounds")
  void sharedParentWithoutExplicitMessageIdProducesTwoCallsAndRounds() {
    String[] events = {
      """
      {"type":"assistant","parentUuid":"shared-parent","message":{"content":"text1"}}\
      """,
      """
      {"type":"assistant","parentUuid":"shared-parent","message":{"content":"text2"}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);
    var rounds = SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions());

    assertThat(artifact.calls()).hasSize(2);
    assertThat(rounds).hasSize(2);
    assertThat(artifact.calls().get(0).turnId()).isNotEqualTo(artifact.calls().get(1).turnId());
  }

  @Test
  @DisplayName("来源文件名中的井号保留，同源分片合并而不同源不合并")
  void sourceNamesWithHashesRemainDistinct() throws Exception {
    JsonNode fragment =
        MAPPER.readTree(
            """
            {"type":"assistant","message":{"id":"m1","content":"piece"}}
            """);
    List<SourceRecord> records = new ArrayList<>();
    records.addAll(
        JsonSourceRecordMapper.toSourceRecords("run#one.jsonl", 0, fragment, "assistant"));
    records.addAll(
        JsonSourceRecordMapper.toSourceRecords("run#one.jsonl", 1, fragment, "assistant"));
    records.addAll(
        JsonSourceRecordMapper.toSourceRecords("run#two.jsonl", 0, fragment, "assistant"));
    var artifact = ENGINE.normalize(NormalizedAgent.QODER, records, List.of(), List.of());
    assertThat(artifact.calls()).hasSize(2);
    assertThat(SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()))
        .hasSize(2);
  }

  @Test
  @DisplayName("边界：不同源文件的同 message.id→2 calls")
  void differentSourceFilesSameMessageIdProduceTwoCalls() {
    // 手动构造来自不同源文件的记录
    var record1 =
        new SourceRecord(
            "one.jsonl#event[0]",
            0,
            "assistant",
            Optional.of("c1"),
            Optional.empty(),
            Optional.empty(),
            Optional.of("m1"),
            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
            "text from one",
            Optional.of("m1"),
            Optional.empty());
    var record2 =
        new SourceRecord(
            "two.jsonl#event[0]",
            0,
            "assistant",
            Optional.of("c2"),
            Optional.empty(),
            Optional.empty(),
            Optional.of("m1"),
            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
            "text from two",
            Optional.of("m1"),
            Optional.empty());

    var artifact =
        ENGINE.normalize(NormalizedAgent.QODER, List.of(record1, record2), List.of(), List.of());
    var rounds = SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions());

    assertThat(artifact.calls()).hasSize(2);
    assertThat(rounds).hasSize(2);
  }

  @Test
  @DisplayName("边界：同 subagentId 不同 parent relation→2 calls")
  void sameSubagentIdDifferentParentRelationProducesTwoCalls() {
    var relation1 =
        new com.feipi.session.browser.domain.source.SourceRecordRelation(
            Optional.of("sub-1"),
            Optional.of("parent-thread-1"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    var relation2 =
        new com.feipi.session.browser.domain.source.SourceRecordRelation(
            Optional.of("sub-1"),
            Optional.of("parent-thread-2"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());

    var record1 =
        new SourceRecord(
            "loc#event[0]",
            0,
            "assistant",
            Optional.of("c1"),
            Optional.empty(),
            Optional.empty(),
            Optional.of("m1"),
            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            relation1,
            "text1",
            Optional.of("m1"),
            Optional.empty());
    var record2 =
        new SourceRecord(
            "loc#event[1]",
            1,
            "assistant",
            Optional.of("c2"),
            Optional.empty(),
            Optional.empty(),
            Optional.of("m1"),
            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            relation2,
            "text2",
            Optional.of("m1"),
            Optional.empty());

    var artifact =
        ENGINE.normalize(NormalizedAgent.QODER, List.of(record1, record2), List.of(), List.of());

    assertThat(artifact.calls()).hasSize(2);
  }

  @Test
  @DisplayName("边界：生成 ID 与原始 ID 碰撞——m1, m1, m1#2 序列→3 calls 无异常")
  void generatedIdsDoNotCollideWithOriginalIds() {
    String[] events = {
      """
      {"type":"assistant","message":{"id":"m1","stop_reason":"end_turn","content":"first"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","stop_reason":"end_turn","content":"second"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1#2","stop_reason":"end_turn","content":"third"}}\
      """,
    };

    NormalizedSessionArtifact artifact = normalizeEvents(events);
    var rounds = SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions());

    assertThat(artifact.calls()).hasSize(3);
    assertThat(rounds).hasSize(3);
    assertThat(artifact.calls()).extracting(NormalizedCall::callId).doesNotHaveDuplicates();
  }

  @Test
  @DisplayName("边界：相同输入重复 normalize 稳定——确定性输出")
  void sameInputProducesStableOutputOnRepeatedNormalization() {
    String[] events = {
      """
      {"type":"user","message":{"content":"go"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","stop_reason":"end_turn","content":"part1"}}\
      """,
      """
      {"type":"assistant","message":{"id":"m1","content":"part2"}}\
      """,
    };

    NormalizedSessionArtifact artifact1 = normalizeEvents(events);
    NormalizedSessionArtifact artifact2 = normalizeEvents(events);

    assertThat(artifact1.calls()).hasSameSizeAs(artifact2.calls());
    for (int i = 0; i < artifact1.calls().size(); i++) {
      assertThat(artifact1.calls().get(i).callId()).isEqualTo(artifact2.calls().get(i).callId());
      assertThat(artifact1.calls().get(i).turnId()).isEqualTo(artifact2.calls().get(i).turnId());
    }
  }

  private static NormalizedSessionArtifact normalizeSynthetic() {
    return normalizeEvents(SYNTHETIC_EVENTS);
  }

  private static NormalizedSessionArtifact normalizeEvents(String[] events) {
    return normalizeEventsAs(events, NormalizedAgent.QODER);
  }

  private static NormalizedSessionArtifact normalizeEventsAs(
      String[] events, NormalizedAgent agent) {
    List<SourceRecord> records = new ArrayList<>();
    for (int i = 0; i < events.length; i++) {
      try {
        JsonNode json = MAPPER.readTree(events[i]);
        String eventType = json.path("type").asText();
        records.addAll(
            JsonSourceRecordMapper.toSourceRecords("synthetic.jsonl", i, json, eventType));
      } catch (Exception e) {
        throw new RuntimeException("Failed to parse event " + i, e);
      }
    }
    return ENGINE.normalize(agent, records, List.of(), List.of());
  }
}
