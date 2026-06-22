package com.feipi.session.browser.artifact.normalized;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.module.SimpleModule;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
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
    return serializeObject(artifact);
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
