package com.feipi.session.browser.index.sqlite;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.enums.CallScope;
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
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * 归一化制品磁盘加载器。
 *
 * <p>从磁盘读取归一化 JSON 制品文件，反序列化为 {@link NormalizedSessionArtifact} 并执行 domain 层验证。 这是唯一的
 * artifact 读取入口，所有消费者必须通过本类加载制品， 避免多处重复解析和验证逻辑。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>文件存在性和可读性在本类入口验证。
 *   <li>JSON 结构和 schema 版本由 {@link NormalizedSessionArtifact} 紧凑构造器验证。
 *   <li>下游 assembler 信任已验证的制品不变量。
 * </ul>
 */
public final class NormalizedArtifactLoader {

  private static final ObjectMapper MAPPER =
      new ObjectMapper()
          .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)
          .configure(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS, true);

  /** 防止外部实例化。 */
  private NormalizedArtifactLoader() {}

  /**
   * 从磁盘路径加载归一化制品。
   *
   * <p>读取 JSON 文件并通过 {@link NormalizedSessionArtifact} 紧凑构造器执行全部 domain 验证。
   *
   * @param artifactPath 制品文件路径
   * @return 已验证的归一化制品
   * @throws IOException 文件不存在、不可读或 JSON 格式错误
   * @throws IllegalArgumentException 当制品未通过 domain 不变量验证时
   */
  public static NormalizedSessionArtifact load(Path artifactPath) throws IOException {
    Objects.requireNonNull(artifactPath, "artifactPath 不得为 null");
    if (!Files.exists(artifactPath)) {
      throw new IOException("归一化制品文件不存在: " + artifactPath);
    }
    if (!Files.isReadable(artifactPath)) {
      throw new IOException("归一化制品文件不可读: " + artifactPath);
    }

    byte[] content = Files.readAllBytes(artifactPath);
    Map<String, Object> root =
        MAPPER.readValue(content, new TypeReference<Map<String, Object>>() {});

    return fromMap(root);
  }

  /**
   * 从已解析的 map 构建归一化制品。
   *
   * <p>用于测试和内存中已有的制品数据。通过 {@link NormalizedSessionArtifact} 紧凑构造器验证不变量。
   *
   * @param root 制品 JSON 根 map
   * @return 已验证的归一化制品
   * @throws IllegalArgumentException 当制品未通过 domain 不变量验证时
   */
  public static NormalizedSessionArtifact fromMap(Map<String, Object> root) {
    Objects.requireNonNull(root, "root 不得为 null");

    String schemaVersion = asString(root, "schemaVersion", NormalizedConstants.SCHEMA_VERSION);
    String agentValue = asString(root, "agent", "");
    NormalizedAgent agent = NormalizedAgent.fromValue(agentValue);

    // session map
    @SuppressWarnings("unchecked")
    Map<String, Object> session =
        root.containsKey("session") ? asMap(root.get("session")) : Map.of();

    // calls 列表
    List<NormalizedCall> calls = parseCalls(root);

    // toolExecutions 列表
    List<NormalizedToolExecution> toolExecutions = parseToolExecutions(root);

    // sourceFiles 列表
    List<NormalizedSourceFile> sourceFiles = parseSourceFiles(root);

    return new NormalizedSessionArtifact(
        schemaVersion,
        agent,
        sourceFiles,
        session,
        calls,
        toolExecutions,
        List.of(),
        Map.of(),
        Map.of());
  }

  /** 解析 calls 列表。 */
  private static List<NormalizedCall> parseCalls(Map<String, Object> root) {
    Object callsObj = root.get("calls");
    if (!(callsObj instanceof List<?> callsList)) {
      return List.of();
    }

    List<NormalizedCall> result = new ArrayList<>();
    for (Object item : callsList) {
      if (!(item instanceof Map<?, ?> callMap)) {
        continue;
      }
      @SuppressWarnings("unchecked")
      Map<String, Object> cm = (Map<String, Object>) callMap;
      result.add(parseCall(cm));
    }
    return result;
  }

  /** 解析单个调用。 */
  private static NormalizedCall parseCall(Map<String, Object> cm) {
    String callId = asString(cm, "callId", "");
    if (callId.isEmpty()) {
      throw new IllegalArgumentException("callId 不得为空");
    }
    int callIndex = asInt(cm, "callIndex", 1);
    if (callIndex < 1) {
      throw new IllegalArgumentException("callIndex 必须 >= 1; got " + callIndex);
    }
    String callKey = asString(cm, "callKey", "C" + callIndex);
    String scopeValue = asString(cm, "scope", "main");
    CallScope scope = parseCallScope(scopeValue);
    Optional<String> parentCallId = optionalString(cm, "parentCallId");
    Optional<String> parentToolCallId = optionalString(cm, "parentToolCallId");
    Optional<String> turnId = optionalString(cm, "turnId");
    String model = asString(cm, "model", "");
    Optional<String> timestamp = optionalString(cm, "timestamp");

    NormalizedCallUsage usage = parseUsage(cm);
    NormalizedCallRequest request = parseRequest(cm);
    NormalizedCallResponse response = parseResponse(cm);

    return new NormalizedCall(
        callId,
        callIndex,
        callKey,
        scope,
        parentCallId,
        parentToolCallId,
        turnId,
        model,
        timestamp,
        usage,
        request,
        response,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  /** 解析调用用量。 */
  private static NormalizedCallUsage parseUsage(Map<String, Object> cm) {
    Object usageObj = cm.get("usage");
    if (!(usageObj instanceof Map<?, ?> usageMap)) {
      return NormalizedCallUsage.empty();
    }
    @SuppressWarnings("unchecked")
    Map<String, Object> um = (Map<String, Object>) usageMap;
    long fresh = asLong(um, "fresh", 0);
    long cacheRead = asLong(um, "cacheRead", 0);
    long cacheWrite = asLong(um, "cacheWrite", 0);
    long output = asLong(um, "output", 0);
    long total = asLong(um, "total", 0);
    return new NormalizedCallUsage(fresh, cacheRead, cacheWrite, output, total);
  }

  /** 解析请求边。 */
  private static NormalizedCallRequest parseRequest(Map<String, Object> cm) {
    Object reqObj = cm.get("request");
    if (!(reqObj instanceof Map<?, ?> reqMap)) {
      return NormalizedCallRequest.empty();
    }
    @SuppressWarnings("unchecked")
    Map<String, Object> rm = (Map<String, Object>) reqMap;
    List<String> toolResultIds = asStringList(rm, "toolResultIds");
    return new NormalizedCallRequest(toolResultIds);
  }

  /** 解析响应边。 */
  private static NormalizedCallResponse parseResponse(Map<String, Object> cm) {
    Object respObj = cm.get("response");
    if (!(respObj instanceof Map<?, ?> respMap)) {
      return NormalizedCallResponse.empty();
    }
    @SuppressWarnings("unchecked")
    Map<String, Object> rm = (Map<String, Object>) respMap;
    List<String> toolCallIds = asStringList(rm, "toolCallIds");
    return new NormalizedCallResponse(toolCallIds);
  }

  /** 解析工具执行列表。 */
  private static List<NormalizedToolExecution> parseToolExecutions(Map<String, Object> root) {
    Object execObj = root.get("toolExecutions");
    if (!(execObj instanceof List<?> execList)) {
      return List.of();
    }

    List<NormalizedToolExecution> result = new ArrayList<>();
    for (Object item : execList) {
      if (!(item instanceof Map<?, ?> execMap)) {
        continue;
      }
      @SuppressWarnings("unchecked")
      Map<String, Object> em = (Map<String, Object>) execMap;
      String toolCallId = asString(em, "toolCallId", "");
      String name = asString(em, "name", "");
      String scopeValue = asString(em, "scope", "main");
      CallScope scope = parseCallScope(scopeValue);
      String declaredByCallId = asString(em, "declaredByCallId", "");
      Optional<String> resultConsumedByCallId = optionalString(em, "resultConsumedByCallId");
      Optional<String> status = optionalString(em, "status");
      Optional<Integer> exitCode = optionalInt(em, "exitCode");
      long durationMs = asLong(em, "durationMs", 0);
      Optional<String> subagentId = optionalString(em, "subagentId");

      result.add(
          new NormalizedToolExecution(
              toolCallId,
              name,
              scope,
              declaredByCallId,
              resultConsumedByCallId,
              status,
              exitCode,
              durationMs,
              List.of(),
              subagentId));
    }
    return result;
  }

  /** 解析源文件列表。 */
  private static List<NormalizedSourceFile> parseSourceFiles(Map<String, Object> root) {
    Object sfObj = root.get("sourceFiles");
    if (!(sfObj instanceof List<?> sfList)) {
      return List.of();
    }

    List<NormalizedSourceFile> result = new ArrayList<>();
    for (Object item : sfList) {
      if (!(item instanceof Map<?, ?> sfMap)) {
        continue;
      }
      @SuppressWarnings("unchecked")
      Map<String, Object> sm = (Map<String, Object>) sfMap;
      String pathStr = asString(sm, "path", "");
      Path filePath = Path.of(pathStr);
      String roleValue = asString(sm, "role", "primary");
      SourceFileRole role = SourceFileRole.fromValue(roleValue);
      Optional<String> subagentId = optionalString(sm, "subagentId");
      Optional<String> parentToolUseId = optionalString(sm, "parentToolUseId");
      result.add(new NormalizedSourceFile(role, filePath, subagentId, parentToolUseId));
    }
    return result;
  }

  private static CallScope parseCallScope(String value) {
    return "subagent".equalsIgnoreCase(value) ? CallScope.SUBAGENT : CallScope.MAIN;
  }

  private static String asString(Map<String, Object> map, String key, String defaultValue) {
    Object value = map.get(key);
    if (value == null) {
      return defaultValue;
    }
    return String.valueOf(value);
  }

  private static int asInt(Map<String, Object> map, String key, int defaultValue) {
    Object value = map.get(key);
    if (value instanceof Number num) {
      return num.intValue();
    }
    if (value != null) {
      try {
        return Integer.parseInt(String.valueOf(value));
      } catch (NumberFormatException e) {
        return defaultValue;
      }
    }
    return defaultValue;
  }

  private static long asLong(Map<String, Object> map, String key, long defaultValue) {
    Object value = map.get(key);
    if (value instanceof Number num) {
      return num.longValue();
    }
    if (value != null) {
      try {
        return Long.parseLong(String.valueOf(value));
      } catch (NumberFormatException e) {
        return defaultValue;
      }
    }
    return defaultValue;
  }

  private static double asDouble(Map<String, Object> map, String key, double defaultValue) {
    Object value = map.get(key);
    if (value instanceof Number num) {
      return num.doubleValue();
    }
    if (value != null) {
      try {
        return Double.parseDouble(String.valueOf(value));
      } catch (NumberFormatException e) {
        return defaultValue;
      }
    }
    return defaultValue;
  }

  private static Optional<String> optionalString(Map<String, Object> map, String key) {
    Object value = map.get(key);
    if (value == null) {
      return Optional.empty();
    }
    String str = String.valueOf(value);
    return str.isEmpty() ? Optional.empty() : Optional.of(str);
  }

  private static Optional<Integer> optionalInt(Map<String, Object> map, String key) {
    Object value = map.get(key);
    if (value instanceof Number num) {
      return Optional.of(num.intValue());
    }
    if (value != null) {
      try {
        return Optional.of(Integer.parseInt(String.valueOf(value)));
      } catch (NumberFormatException e) {
        return Optional.empty();
      }
    }
    return Optional.empty();
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> asMap(Object value) {
    if (value instanceof Map<?, ?> m) {
      return (Map<String, Object>) m;
    }
    return Map.of();
  }

  /** 从 map 中读取字符串列表。 */
  @SuppressWarnings("unchecked")
  private static List<String> asStringList(Map<String, Object> map, String key) {
    Object value = map.get(key);
    if (value instanceof List<?> list) {
      List<String> result = new ArrayList<>();
      for (Object item : list) {
        if (item != null) {
          result.add(String.valueOf(item));
        }
      }
      return result;
    }
    return List.of();
  }
}
