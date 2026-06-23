package com.feipi.session.browser.contracttest.normalized;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 归一化复合类型合约测试。
 *
 * <p>覆盖 {@link SourceUnitRefRange}、{@link SourceUnitCatalogEntry}、{@link NormalizedCall}、 {@link
 * NormalizedToolExecution}、{@link NormalizedSessionArtifact} 的不变量正负向路径。 同时覆盖 {@link
 * NormalizedAgent} 和 {@link SourceUnitDirection} 枚举。
 */
@DisplayName("归一化复合类型合约测试")
class NormalizedCompositeContractTest {

  @Nested
  @DisplayName("NormalizedAgent 枚举合约")
  class NormalizedAgentContract {

    @Test
    @DisplayName("正向：合法 agent 值可解析")
    void validAgentValues() {
      assertThat(NormalizedAgent.fromValue("claude_code")).isEqualTo(NormalizedAgent.CLAUDE_CODE);
      assertThat(NormalizedAgent.fromValue("codex")).isEqualTo(NormalizedAgent.CODEX);
      assertThat(NormalizedAgent.fromValue("qoder")).isEqualTo(NormalizedAgent.QODER);
    }

    @Test
    @DisplayName("正向：getValue() 返回 Python 兼容值")
    void getValueCompat() {
      assertThat(NormalizedAgent.CLAUDE_CODE.getValue()).isEqualTo("claude_code");
      assertThat(NormalizedAgent.CODEX.getValue()).isEqualTo("codex");
      assertThat(NormalizedAgent.QODER.getValue()).isEqualTo("qoder");
    }

    @Test
    @DisplayName("负向：非法 agent 值抛出异常")
    void invalidAgentValue() {
      assertThatThrownBy(() -> NormalizedAgent.fromValue("invalid_agent"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("invalid normalized agent");
    }
  }

  @Nested
  @DisplayName("SourceUnitDirection 枚举合约")
  class SourceUnitDirectionContract {

    @Test
    @DisplayName("正向：合法 direction 值可解析")
    void validDirectionValues() {
      assertThat(SourceUnitDirection.fromValue("request")).isEqualTo(SourceUnitDirection.REQUEST);
      assertThat(SourceUnitDirection.fromValue("response")).isEqualTo(SourceUnitDirection.RESPONSE);
    }

    @Test
    @DisplayName("负向：非法 direction 值抛出异常")
    void invalidDirectionValue() {
      assertThatThrownBy(() -> SourceUnitDirection.fromValue("unknown"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("invalid source unit direction");
    }
  }

  @Nested
  @DisplayName("SourceUnitRefRange 合约")
  class SourceUnitRefRangeContract {

    @Test
    @DisplayName("正向：合法范围构造成功")
    void validRange() {
      SourceUnitRefRange range =
          new SourceUnitRefRange(
              Optional.of("seq1"), 0, 5, List.of("unit1"), Optional.of("display"));
      assertThat(range.start()).isZero();
      assertThat(range.end()).isEqualTo(5);
      assertThat(range.refs()).containsExactly("unit1");
    }

    @Test
    @DisplayName("负向：start 为负数抛出异常")
    void negativeStart() {
      assertThatThrownBy(
              () -> new SourceUnitRefRange(Optional.empty(), -1, 0, List.of(), Optional.empty()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("start");
    }

    @Test
    @DisplayName("负向：end 小于 start 抛出异常")
    void endLessThanStart() {
      assertThatThrownBy(
              () -> new SourceUnitRefRange(Optional.empty(), 10, 5, List.of(), Optional.empty()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("end must be >= start");
    }
  }

  @Nested
  @DisplayName("SourceUnitCatalogEntry 合约")
  class SourceUnitCatalogEntryContract {

    private SourceUnitCatalogEntry createValidEntry() {
      return new SourceUnitCatalogEntry(
          "unit-1",
          "/path/to/file",
          "locator-1",
          "text",
          "user_input",
          SourceUnitDirection.REQUEST,
          0,
          0,
          ByteRange.empty(),
          "hash-abc",
          Optional.empty(),
          Optional.empty(),
          50,
          Optional.empty(),
          Optional.empty(),
          null,
          Optional.empty(),
          Optional.empty(),
          List.of());
    }

    @Test
    @DisplayName("正向：合法目录条目构造成功")
    void validEntry() {
      SourceUnitCatalogEntry entry = createValidEntry();
      assertThat(entry.unitKey()).isEqualTo("unit-1");
      assertThat(entry.direction()).isEqualTo(SourceUnitDirection.REQUEST);
    }

    @Test
    @DisplayName("负向：unitKey 为 null 抛出异常")
    void nullUnitKey() {
      assertThatThrownBy(
              () ->
                  new SourceUnitCatalogEntry(
                      null,
                      "/path",
                      "locator",
                      "type",
                      "candidate",
                      SourceUnitDirection.REQUEST,
                      0,
                      0,
                      ByteRange.empty(),
                      "hash",
                      Optional.empty(),
                      Optional.empty(),
                      50,
                      Optional.empty(),
                      Optional.empty(),
                      null,
                      Optional.empty(),
                      Optional.empty(),
                      List.of()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("unitKey");
    }

    @Test
    @DisplayName("负向：direction 为 null 抛出异常")
    void nullDirection() {
      assertThatThrownBy(
              () ->
                  new SourceUnitCatalogEntry(
                      "key",
                      "/path",
                      "locator",
                      "type",
                      "candidate",
                      null,
                      0,
                      0,
                      ByteRange.empty(),
                      "hash",
                      Optional.empty(),
                      Optional.empty(),
                      50,
                      Optional.empty(),
                      Optional.empty(),
                      null,
                      Optional.empty(),
                      Optional.empty(),
                      List.of()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("direction");
    }

    @Test
    @DisplayName("负向：eventOrder 为负数抛出异常")
    void negativeEventOrder() {
      assertThatThrownBy(
              () ->
                  new SourceUnitCatalogEntry(
                      "key",
                      "/path",
                      "locator",
                      "type",
                      "candidate",
                      SourceUnitDirection.REQUEST,
                      -1,
                      0,
                      ByteRange.empty(),
                      "hash",
                      Optional.empty(),
                      Optional.empty(),
                      50,
                      Optional.empty(),
                      Optional.empty(),
                      null,
                      Optional.empty(),
                      Optional.empty(),
                      List.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("eventOrder");
    }

    @Test
    @DisplayName("负向：byteRange 为 null 抛出异常")
    void nullByteRange() {
      assertThatThrownBy(
              () ->
                  new SourceUnitCatalogEntry(
                      "key",
                      "/path",
                      "locator",
                      "type",
                      "candidate",
                      SourceUnitDirection.REQUEST,
                      0,
                      0,
                      null,
                      "hash",
                      Optional.empty(),
                      Optional.empty(),
                      50,
                      Optional.empty(),
                      Optional.empty(),
                      null,
                      Optional.empty(),
                      Optional.empty(),
                      List.of()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("byteRange");
    }
  }

  @Nested
  @DisplayName("NormalizedCall 合约")
  class NormalizedCallContract {

    private NormalizedCall createValidCall() {
      return new NormalizedCall(
          "call-1",
          1,
          "C1",
          CallScope.MAIN,
          Optional.empty(),
          Optional.empty(),
          Optional.empty(),
          "claude-3",
          Optional.empty(),
          NormalizedCallUsage.empty(),
          NormalizedCallRequest.empty(),
          NormalizedCallResponse.empty(),
          List.of(),
          List.of(),
          Map.of(),
          Map.of());
    }

    @Test
    @DisplayName("正向：合法调用构造成功")
    void validCall() {
      NormalizedCall call = createValidCall();
      assertThat(call.callId()).isEqualTo("call-1");
      assertThat(call.callIndex()).isEqualTo(1);
      assertThat(call.callKey()).isEqualTo("C1");
    }

    @Test
    @DisplayName("负向：callId 为 null 抛出异常")
    void nullCallId() {
      assertThatThrownBy(
              () ->
                  new NormalizedCall(
                      null,
                      1,
                      "C1",
                      CallScope.MAIN,
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      "model",
                      Optional.empty(),
                      NormalizedCallUsage.empty(),
                      NormalizedCallRequest.empty(),
                      NormalizedCallResponse.empty(),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("callId");
    }

    @Test
    @DisplayName("负向：callId 为空字符串抛出异常")
    void emptyCallId() {
      assertThatThrownBy(
              () ->
                  new NormalizedCall(
                      "",
                      1,
                      "C1",
                      CallScope.MAIN,
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      "model",
                      Optional.empty(),
                      NormalizedCallUsage.empty(),
                      NormalizedCallRequest.empty(),
                      NormalizedCallResponse.empty(),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("callId");
    }

    @Test
    @DisplayName("负向：callIndex < 1 抛出异常")
    void invalidCallIndex() {
      assertThatThrownBy(
              () ->
                  new NormalizedCall(
                      "call-1",
                      0,
                      "C0",
                      CallScope.MAIN,
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      "model",
                      Optional.empty(),
                      NormalizedCallUsage.empty(),
                      NormalizedCallRequest.empty(),
                      NormalizedCallResponse.empty(),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("callIndex");
    }

    @Test
    @DisplayName("负向：callKey 不匹配 callIndex 抛出异常")
    void mismatchedCallKey() {
      assertThatThrownBy(
              () ->
                  new NormalizedCall(
                      "call-1",
                      1,
                      "C2",
                      CallScope.MAIN,
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      "model",
                      Optional.empty(),
                      NormalizedCallUsage.empty(),
                      NormalizedCallRequest.empty(),
                      NormalizedCallResponse.empty(),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("callKey");
    }
  }

  @Nested
  @DisplayName("NormalizedToolExecution 合约")
  class NormalizedToolExecutionContract {

    @Test
    @DisplayName("正向：合法工具执行构造成功")
    void validExecution() {
      NormalizedToolExecution exec =
          new NormalizedToolExecution(
              "tool-1",
              "Bash",
              CallScope.MAIN,
              "call-1",
              Optional.of("call-2"),
              Optional.empty(),
              Optional.empty(),
              100,
              List.of("/tmp/file"),
              Optional.empty());
      assertThat(exec.toolCallId()).isEqualTo("tool-1");
      assertThat(exec.durationMs()).isEqualTo(100);
    }

    @Test
    @DisplayName("负向：toolCallId 为空字符串抛出异常")
    void emptyToolCallId() {
      assertThatThrownBy(
              () ->
                  new NormalizedToolExecution(
                      "",
                      "Bash",
                      CallScope.MAIN,
                      "call-1",
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      0,
                      List.of(),
                      Optional.empty()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("toolCallId");
    }

    @Test
    @DisplayName("负向：durationMs 为负数抛出异常")
    void negativeDuration() {
      assertThatThrownBy(
              () ->
                  new NormalizedToolExecution(
                      "tool-1",
                      "Bash",
                      CallScope.MAIN,
                      "call-1",
                      Optional.empty(),
                      Optional.empty(),
                      Optional.empty(),
                      -1,
                      List.of(),
                      Optional.empty()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("durationMs");
    }
  }

  @Nested
  @DisplayName("NormalizedSessionArtifact 合约")
  class NormalizedSessionArtifactContract {

    private NormalizedSessionArtifact createValidArtifact() {
      return new NormalizedSessionArtifact(
          NormalizedConstants.SCHEMA_VERSION,
          NormalizedAgent.CLAUDE_CODE,
          List.of(),
          Map.of("session_id", "s1"),
          List.of(),
          List.of(),
          List.of(),
          Map.of(),
          Map.of());
    }

    @Test
    @DisplayName("正向：合法制品构造成功")
    void validArtifact() {
      NormalizedSessionArtifact artifact = createValidArtifact();
      assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
      assertThat(artifact.agent()).isEqualTo(NormalizedAgent.CLAUDE_CODE);
    }

    @Test
    @DisplayName("负向：错误 schema 版本抛出异常")
    void wrongSchemaVersion() {
      assertThatThrownBy(
              () ->
                  new NormalizedSessionArtifact(
                      "wrong-version",
                      NormalizedAgent.CLAUDE_CODE,
                      List.of(),
                      Map.of("session_id", "s1"),
                      List.of(),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("schemaVersion");
    }

    @Test
    @DisplayName("负向：agent 为 null 抛出异常")
    void nullAgent() {
      assertThatThrownBy(
              () ->
                  new NormalizedSessionArtifact(
                      NormalizedConstants.SCHEMA_VERSION,
                      null,
                      List.of(),
                      Map.of("session_id", "s1"),
                      List.of(),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("agent");
    }

    @Test
    @DisplayName("负向：重复 callId 抛出异常")
    void duplicateCallIds() {
      NormalizedCall call1 =
          new NormalizedCall(
              "dup-id",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "model",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      NormalizedCall call2 =
          new NormalizedCall(
              "dup-id",
              2,
              "C2",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "model",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());

      assertThatThrownBy(
              () ->
                  new NormalizedSessionArtifact(
                      NormalizedConstants.SCHEMA_VERSION,
                      NormalizedAgent.CLAUDE_CODE,
                      List.of(),
                      Map.of("session_id", "s1"),
                      List.of(call1, call2),
                      List.of(),
                      List.of(),
                      Map.of(),
                      Map.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("callId values must be unique");
    }

    @Test
    @DisplayName("正向：防御性拷贝，外部修改不影响内部")
    void defensiveCopy() {
      var mutableCalls = new java.util.ArrayList<NormalizedCall>();
      NormalizedSessionArtifact artifact =
          new NormalizedSessionArtifact(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CLAUDE_CODE,
              List.of(),
              Map.of("session_id", "s1"),
              mutableCalls,
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      // 外部列表修改不影响内部
      assertThat(artifact.calls()).isEmpty();
    }
  }

  @Nested
  @DisplayName("NormalizedSourceFile 合约")
  class NormalizedSourceFileContract {

    @Test
    @DisplayName("正向：合法源文件构造成功")
    void validSourceFile() {
      NormalizedSourceFile file =
          new NormalizedSourceFile(
              SourceFileRole.TRANSCRIPT,
              Path.of("/path/to/file.json"),
              Optional.empty(),
              Optional.empty());
      assertThat(file.role()).isEqualTo(SourceFileRole.TRANSCRIPT);
      assertThat(file.path()).isEqualTo(Path.of("/path/to/file.json"));
    }

    @Test
    @DisplayName("负向：role 为 null 抛出异常")
    void nullRole() {
      assertThatThrownBy(
              () ->
                  new NormalizedSourceFile(
                      null, Path.of("/path"), Optional.empty(), Optional.empty()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("role");
    }

    @Test
    @DisplayName("负向：path 为 null 抛出异常")
    void nullPath() {
      assertThatThrownBy(
              () ->
                  new NormalizedSourceFile(
                      SourceFileRole.TRANSCRIPT, null, Optional.empty(), Optional.empty()))
          .isInstanceOf(NullPointerException.class)
          .hasMessageContaining("path");
    }
  }
}
