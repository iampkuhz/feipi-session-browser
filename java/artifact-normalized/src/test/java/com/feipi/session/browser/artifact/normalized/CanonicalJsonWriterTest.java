package com.feipi.session.browser.artifact.normalized;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link CanonicalJsonWriter} 确定性序列化合约测试。 */
@DisplayName("CanonicalJsonWriter 确定性序列化测试")
class CanonicalJsonWriterTest {

  private CanonicalJsonWriter writer;

  @BeforeEach
  void setUp() {
    writer = new CanonicalJsonWriter();
  }

  @Test
  @DisplayName("确定性：同一 artifact 序列化两次得到完全相同的 byte[]")
  void deterministicSameArtifactProducesIdenticalBytes() {
    NormalizedSessionArtifact artifact = createMinimalArtifact("test-session-001");
    byte[] first = writer.serialize(artifact);
    byte[] second = writer.serialize(artifact);
    assertThat(first).isEqualTo(second);
  }

  @Test
  @DisplayName("确定性：两个相同内容的不同实例产生相同字节")
  void deterministicEqualArtifactsProduceIdenticalBytes() {
    NormalizedSessionArtifact a = createMinimalArtifact("test-session-001");
    NormalizedSessionArtifact b = createMinimalArtifact("test-session-001");
    assertThat(writer.serialize(a)).isEqualTo(writer.serialize(b));
  }

  @Test
  @DisplayName("Map 排序：key 按字母排序")
  void mapKeysSortedAlphabetically() {
    Map<String, Object> session = new LinkedHashMap<>();
    session.put("zebra", "z");
    session.put("alpha", "a");
    session.put("middle", "m");
    session.put("session_key", "test-key");

    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            session,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, StandardCharsets.UTF_8);

    // 验证 session 内的 key 按字母排序
    int alphaIdx = json.indexOf("\"alpha\"");
    int middleIdx = json.indexOf("\"middle\"");
    int zebraIdx = json.indexOf("\"zebra\"");
    assertThat(alphaIdx).isLessThan(middleIdx);
    assertThat(middleIdx).isLessThan(zebraIdx);
  }

  @Test
  @DisplayName("UTF-8 编码：中文内容正确编码")
  void utf8ChineseContentEncodedCorrectly() {
    Map<String, Object> session = Map.of("session_key", "test-key", "title", "测试会话");
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            session,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, StandardCharsets.UTF_8);
    assertThat(json).contains("测试会话");
  }

  @Test
  @DisplayName("UTF-8 编码：emoji 内容正确编码（round-trip 验证）")
  void utf8EmojiContentEncodedCorrectly() {
    Map<String, Object> session = Map.of("session_key", "test-key", "emoji", "hello 🌍");
    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            session,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, StandardCharsets.UTF_8);

    // Jackson 可能将增补字符编码为代理对转义（🌍），
    // 这是合法 JSON。验证往返正确性：解析后应得到原始表情符号。
    assertThat(json).contains("hello");
    // 验证 JSON 可以被正确解析并还原表情符号
    com.fasterxml.jackson.databind.ObjectMapper parser =
        new com.fasterxml.jackson.databind.ObjectMapper();
    try {
      com.fasterxml.jackson.databind.JsonNode root = parser.readTree(bytes);
      String emojiValue = root.at("/session/emoji").asText();
      assertThat(emojiValue).isEqualTo("hello 🌍");
    } catch (java.io.IOException e) {
      throw new AssertionError("JSON 解析失败", e);
    }
  }

  @Test
  @DisplayName("空集合：空 list 序列化为 []，空 map 序列化为 {}")
  void emptyCollectionsSerializedAsEmptyBrackets() {
    NormalizedSessionArtifact artifact = createMinimalArtifact("test-key");
    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, StandardCharsets.UTF_8);

    // sourceFiles 为空 list，应该序列化为 []
    assertThat(json).contains("\"sourceFiles\":[]");
    // 调用列表为空
    assertThat(json).contains("\"calls\":[]");
    // toolExecutions 为空 list
    assertThat(json).contains("\"toolExecutions\":[]");
    // 诊断信息列表为空
    assertThat(json).contains("\"diagnostics\":[]");
  }

  @Test
  @DisplayName("数字精度：long 值不使用科学计数法")
  void numberPrecisionLongValuesNoScientificNotation() {
    NormalizedCallUsage usage =
        new NormalizedCallUsage(100000L, 200000L, 300000L, 400000L, 1000000L);
    NormalizedCall call =
        new NormalizedCall(
            "call-001",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            "claude-3-opus",
            Optional.empty(),
            usage,
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            Map.of("session_key", "test-key"),
            List.of(call),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, StandardCharsets.UTF_8);
    // 大数值不应包含科学计数法
    assertThat(json).contains("100000");
    assertThat(json).contains("1000000");
    assertThat(json).doesNotContain("E+").doesNotContain("e+");
  }

  @Test
  @DisplayName("Optional 字段：present 序列化值，empty 序列化 null")
  void optionalFieldPresentAndEmpty() {
    NormalizedCall call =
        new NormalizedCall(
            "call-001",
            1,
            "C1",
            CallScope.MAIN,
            Optional.of("parent-call-001"),
            Optional.empty(),
            Optional.empty(),
            "claude-3-opus",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    NormalizedSessionArtifact artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CLAUDE_CODE,
            List.of(),
            Map.of("session_key", "test-key"),
            List.of(call),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());

    byte[] bytes = writer.serialize(artifact);
    String json = new String(bytes, StandardCharsets.UTF_8);
    // parentCallId 有值 → 序列化值
    assertThat(json).contains("\"parentCallId\":\"parent-call-001\"");
    // parentToolCallId 为空 → 序列化 null
    assertThat(json).contains("\"parentToolCallId\":null");
  }

  @Test
  @DisplayName("UTF-8 编码：输出字节为有效 UTF-8")
  void utf8OutputIsValidUtf8() {
    NormalizedSessionArtifact artifact = createMinimalArtifact("test-key");
    byte[] bytes = writer.serialize(artifact);
    // 验证可以无损解码为 UTF-8 字符串
    String decoded = new String(bytes, StandardCharsets.UTF_8);
    byte[] reencoded = decoded.getBytes(StandardCharsets.UTF_8);
    assertThat(reencoded).isEqualTo(bytes);
  }

  private static NormalizedSessionArtifact createMinimalArtifact(String sessionKey) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of("session_key", sessionKey),
        List.of(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
