package com.feipi.session.browser.scan.artifact;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/**
 * 确定性 JSON 序列化器。
 *
 * <p>将 {@link NormalizedSessionArtifact} 序列化为字节数组，保证相同输入始终产生相同字节输出。 配置要点：
 *
 * <ul>
 *   <li>Map key 按字母排序（{@link SerializationFeature#ORDER_MAP_ENTRIES_BY_KEYS}）。
 *   <li>严格重复检测（{@link JsonGenerator.Feature#STRICT_DUPLICATE_DETECTION}）。
 *   <li>关闭格式化输出，生成紧凑 JSON。
 *   <li>编码固定 UTF-8。
 *   <li>BigDecimal 不使用科学计数法。
 * </ul>
 *
 * <p>该类是线程安全的，{@link ObjectMapper} 实例由 Jackson 保证线程安全。
 */
public final class CanonicalJsonWriter {

  private final ObjectMapper mapper;

  /** 创建使用默认配置的确定性 JSON 写入器。 */
  @SuppressWarnings({"unchecked", "rawtypes"})
  public CanonicalJsonWriter() {
    JsonFactory factory = new JsonFactory();
    // 严格重复检测
    factory.configure(JsonGenerator.Feature.STRICT_DUPLICATE_DETECTION, true);
    // BigDecimal 不使用科学计数法
    factory.configure(JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN, true);

    this.mapper = new ObjectMapper(factory);

    // 确定性配置
    mapper.configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
    mapper.configure(SerializationFeature.INDENT_OUTPUT, false);

    // 注册 Optional 序列化器：有值 → 内值，为空 → null
    JsonSerializer<Optional<?>> optionalSerializer =
        new JsonSerializer<Optional<?>>() {
          @Override
          public void serialize(
              Optional<?> value, JsonGenerator gen, SerializerProvider serializers)
              throws IOException {
            if (value.isPresent()) {
              serializers.defaultSerializeValue(value.get(), gen);
            } else {
              gen.writeNull();
            }
          }
        };
    SimpleModule optionalModule = new SimpleModule("optional-module");
    optionalModule.addSerializer((Class) Optional.class, optionalSerializer);
    mapper.registerModule(optionalModule);

    // 注册域枚举序列化器：输出 enum.getValue() 而非 enum.name()
    SimpleModule domainModule = new SimpleModule("domain-module");
    domainModule.addSerializer(
        NormalizedAgent.class,
        new JsonSerializer<NormalizedAgent>() {
          @Override
          public void serialize(NormalizedAgent v, JsonGenerator gen, SerializerProvider sp)
              throws IOException {
            gen.writeString(v.getValue());
          }
        });
    domainModule.addSerializer(
        CallScope.class,
        new JsonSerializer<CallScope>() {
          @Override
          public void serialize(CallScope v, JsonGenerator gen, SerializerProvider sp)
              throws IOException {
            gen.writeString(v.getValue());
          }
        });
    domainModule.addSerializer(
        SourceUnitDirection.class,
        new JsonSerializer<SourceUnitDirection>() {
          @Override
          public void serialize(SourceUnitDirection v, JsonGenerator gen, SerializerProvider sp)
              throws IOException {
            gen.writeString(v.getValue());
          }
        });
    domainModule.addSerializer(
        SourceFileRole.class,
        new JsonSerializer<SourceFileRole>() {
          @Override
          public void serialize(SourceFileRole v, JsonGenerator gen, SerializerProvider sp)
              throws IOException {
            gen.writeString(v.getValue());
          }
        });
    // 注册 Path 序列化器：输出 path.toString()
    domainModule.addSerializer(
        Path.class,
        new JsonSerializer<Path>() {
          @Override
          public void serialize(Path v, JsonGenerator gen, SerializerProvider sp)
              throws IOException {
            gen.writeString(v.toString());
          }
        });
    mapper.registerModule(domainModule);
  }

  /**
   * 将归一化制品序列化为确定性字节数组。
   *
   * <p>同一 {@link NormalizedSessionArtifact} 实例多次调用返回完全相同的字节数组。 编码固定为 UTF-8。
   *
   * @param artifact 要序列化的归一化制品，不得为 null
   * @return UTF-8 编码的确定性 JSON 字节数组
   * @throws UncheckedIOException 当序列化过程发生 I/O 错误时
   */
  public byte[] serialize(NormalizedSessionArtifact artifact) {
    return serializeObject(toCanonicalMap(artifact));
  }

  private static Map<String, Object> toCanonicalMap(NormalizedSessionArtifact artifact) {
    Map<String, Object> root = new LinkedHashMap<>();
    root.put("schema_version", artifact.schemaVersion());
    root.put("agent", artifact.agent().getValue());
    root.put(
        "source",
        Map.of(
            "files",
            artifact.sourceFiles().stream()
                .map(sourceFile -> sourceFileMap(artifact.agent(), sourceFile))
                .toList()));
    root.put("session", artifact.session().toMap());
    root.put("calls", artifact.calls().stream().map(CanonicalJsonWriter::callMap).toList());
    root.put(
        "tool_executions",
        artifact.toolExecutions().stream().map(CanonicalJsonWriter::toolExecutionMap).toList());
    root.put(
        "diagnostics",
        artifact.diagnostics().stream().map(CanonicalJsonWriter::diagnosticMap).toList());
    if (!artifact.sourceUnitCatalog().isEmpty()) {
      root.put("source_unit_catalog", artifact.sourceUnitCatalog());
    }
    if (!artifact.sourceUnitSequences().isEmpty()) {
      root.put("source_unit_sequences", artifact.sourceUnitSequences());
    }
    return root;
  }

  private static Map<String, Object> sourceFileMap(
      NormalizedAgent agent, NormalizedSourceFile sourceFile) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("role", sourceFileRoleValue(agent, sourceFile));
    map.put("path", sourceFile.path().toString());
    putOptional(map, "subagent_id", sourceFile.subagentId());
    putOptional(map, "parent_tool_use_id", sourceFile.parentToolUseId());
    return map;
  }

  private static String sourceFileRoleValue(
      NormalizedAgent agent, NormalizedSourceFile sourceFile) {
    if (sourceFile.role() == SourceFileRole.TRANSCRIPT) {
      return agent == NormalizedAgent.CODEX ? "codex_rollout" : "main_session";
    }
    return sourceFile.role().getValue();
  }

  private static Map<String, Object> callMap(NormalizedCall call) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("call_id", call.callId());
    map.put("call_index", call.callIndex());
    map.put("call_key", call.callKey());
    map.put("scope", call.scope().getValue());
    map.put("parent_call_id", optionalString(call.parentCallId()));
    map.put("parent_tool_call_id", optionalString(call.parentToolCallId()));
    map.put("turn_id", optionalString(call.turnId()));
    map.put("model", call.model());
    map.put("timestamp", optionalString(call.timestamp()));
    map.put("usage", usageMap(call));
    map.put("request", Map.of("tool_result_ids", call.request().toolResultIds()));
    map.put("response", Map.of("tool_call_ids", call.response().toolCallIds()));
    if (!call.sourceUnitRefRanges().isEmpty()) {
      map.put(
          "source_unit_ref_ranges",
          call.sourceUnitRefRanges().stream()
              .map(CanonicalJsonWriter::sourceUnitRefRangeMap)
              .toList());
    }
    if (!call.sourceUnits().isEmpty()) {
      map.put("source_units", call.sourceUnits());
    }
    if (!call.attributionCandidates().isEmpty()) {
      map.put("attribution_candidates", call.attributionCandidates());
    }
    if (!call.usageSource().isEmpty()) {
      map.put("usage_source", call.usageSource());
    }
    putOptional(map, "subagent_id", call.subagentId());
    putOptional(map, "parent_tool_name", call.parentToolName());
    return map;
  }

  private static Map<String, Object> usageMap(NormalizedCall call) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("fresh", call.usage().fresh());
    map.put("cache_read", call.usage().cacheRead());
    map.put("cache_write", call.usage().cacheWrite());
    map.put("output", call.usage().output());
    map.put("total", call.usage().total());
    return map;
  }

  private static Map<String, Object> sourceUnitRefRangeMap(SourceUnitRefRange refRange) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("sequence", optionalString(refRange.sequence()));
    map.put("start", refRange.start());
    map.put("end", refRange.end());
    map.put("refs", refRange.refs());
    map.put("role", optionalString(refRange.role()));
    return map;
  }

  private static Map<String, Object> toolExecutionMap(NormalizedToolExecution tool) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("tool_call_id", tool.toolCallId());
    map.put("name", tool.name());
    map.put("scope", tool.scope().getValue());
    map.put("declared_by_call_id", tool.declaredByCallId());
    map.put("result_consumed_by_call_id", optionalString(tool.resultConsumedByCallId()));
    putOptional(map, "status", tool.status());
    tool.exitCode().ifPresent(exitCode -> map.put("exit_code", exitCode));
    if (tool.durationMs() > 0L) {
      map.put("duration_ms", tool.durationMs());
    }
    if (!tool.filesTouched().isEmpty()) {
      map.put("files_touched", tool.filesTouched());
    }
    putOptional(map, "subagent_id", tool.subagentId());
    return map;
  }

  private static Map<String, Object> diagnosticMap(
      com.feipi.session.browser.domain.normalized.NormalizedDiagnostic diagnostic) {
    Map<String, Object> source = diagnostic.toMap();
    Map<String, Object> map = new LinkedHashMap<>();
    for (Map.Entry<String, Object> entry : source.entrySet()) {
      map.put(toSnakeCase(entry.getKey()), entry.getValue());
    }
    return map;
  }

  private static String optionalString(Optional<String> value) {
    return value == null ? "" : value.orElse("");
  }

  private static void putOptional(
      Map<String, Object> map, String key, Optional<String> optionalValue) {
    if (optionalValue != null && optionalValue.isPresent()) {
      map.put(key, optionalValue.get());
    }
  }

  private static String toSnakeCase(String value) {
    return value.replaceAll("([A-Z])", "_$1").toLowerCase(Locale.ROOT);
  }

  /**
   * 将任意对象序列化为确定性字节数组（模块内部使用）。
   *
   * @param value 要序列化的对象
   * @return UTF-8 编码的确定性 JSON 字节数组
   */
  byte[] serializeObject(Object value) {
    try {
      ByteArrayOutputStream baos = new ByteArrayOutputStream();
      mapper.writeValue(baos, value);
      return baos.toByteArray();
    } catch (IOException e) {
      throw new UncheckedIOException("JSON 序列化失败", e);
    }
  }
}
