package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;
import java.util.Optional;

/**
 * 源中性的已解析事件记录。
 *
 * <p>该模型是 adapter parse 阶段与 normalization engine 之间的共享 core model。它只承载归一化所需的稳定字段，不保存 Jackson {@code
 * JsonNode}、SQLite row、文件句柄或 provider 原始 payload。locator 应为可复现定位标识，不得把绝对 home path 作为长期身份。
 *
 * @param locator 源记录定位符，来源于相对路径/会话内偏移等稳定信息
 * @param eventIndex 事件在源输入中的序号，从 0 开始
 * @param eventType 源中性事件类型，未知时为 {@code "unknown"}
 * @param callId 助手调用标识，缺失时为空
 * @param model 模型标识，缺失时为空
 * @param timestamp provider 原始时间戳文本，缺失时为空；时区语义保留在原始文本中
 * @param turnId 会话轮次标识，缺失时为空
 * @param usage token 用量分量，缺失分量为 0
 * @param toolCalls 该记录声明的工具调用列表，保持源内顺序
 * @param toolUseId 工具结果引用的工具调用标识，缺失时为空
 * @param toolName 独立工具调用记录的工具名称，缺失时为空
 * @param toolError 工具结果中的错误信息，非空表示工具执行失败；缺失时为空
 * @param relation 该记录携带的父子关系证据，缺失时为空关系
 */
@DomainModel
public record SourceRecord(
    /* 源记录定位符，来源于相对路径/会话内偏移等稳定信息。 */
    @NotBlank String locator,

    /* 事件在源输入中的序号，从 0 开始。 */
    @PositiveOrZero int eventIndex,

    /* 源中性事件类型，未知时为 {@code "unknown"}。 */
    @NotNull String eventType,

    /* 助手调用标识，缺失时为空。 */
    @NotNull Optional<String> callId,

    /* 模型标识，缺失时为空。 */
    @NotNull Optional<String> model,

    /* provider 原始时间戳文本，缺失时为空；时区语义保留在原始文本中。 */
    @NotNull Optional<String> timestamp,

    /* 会话轮次标识，缺失时为空。 */
    @NotNull Optional<String> turnId,

    /* token 用量分量，缺失分量为 0。 */
    @NotNull SourceRecordUsage usage,

    /* 该记录声明的工具调用列表，保持源内顺序。 */
    @NotNull List<SourceToolCall> toolCalls,

    /* 工具结果引用的工具调用标识，缺失时为空。 */
    @NotNull Optional<String> toolUseId,

    /* 独立工具调用记录的工具名称，缺失时为空。 */
    @NotNull Optional<String> toolName,

    /* 工具结果中的错误信息，非空表示工具执行失败；缺失时为空。 */
    @NotNull Optional<String> toolError,

    /* 该记录携带的父子关系证据，缺失时为空关系。 */
    @NotNull SourceRecordRelation relation) {

  /**
   * 兼容旧调用点的构造器。
   *
   * <p>未显式传入关系时使用空关系。
   */
  public SourceRecord(
      String locator,
      int eventIndex,
      String eventType,
      Optional<String> callId,
      Optional<String> model,
      Optional<String> timestamp,
      Optional<String> turnId,
      SourceRecordUsage usage,
      List<SourceToolCall> toolCalls,
      Optional<String> toolUseId,
      Optional<String> toolName,
      Optional<String> toolError) {
    this(
        locator,
        eventIndex,
        eventType,
        callId,
        model,
        timestamp,
        turnId,
        usage,
        toolCalls,
        toolUseId,
        toolName,
        toolError,
        SourceRecordRelation.empty());
  }

  /**
   * 紧凑构造器，处理默认值并校验约束。
   *
   * <p>当 {@code eventType} 为空时默认为 {@code "unknown"}。
   */
  public SourceRecord {
    // eventType 默认值处理
    if (eventType == null || eventType.isBlank()) {
      eventType = "unknown";
    }
    // 集合防御性拷贝
    toolCalls = List.copyOf(toolCalls);
    try {
      ValidationSupport.validateCanonicalConstructor(
          SourceRecord.class,
          locator,
          eventIndex,
          eventType,
          callId,
          model,
          timestamp,
          turnId,
          usage,
          toolCalls,
          toolUseId,
          toolName,
          toolError,
          relation);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 创建只包含基础定位和类型信息的源记录。
   *
   * @param locator 源记录定位符
   * @param eventIndex 事件在源输入中的序号
   * @param eventType 源中性事件类型
   * @return 源中性记录
   */
  public static SourceRecord of(String locator, int eventIndex, String eventType) {
    return new SourceRecord(
        locator,
        eventIndex,
        eventType,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty());
  }

  /**
   * 将 Jakarta 校验违规翻译为向后兼容的异常类型。
   *
   * @param e 原始校验违规异常
   */
  private static void translateValidation(ConstraintViolationException e) {
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      String field = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        throw new NullPointerException(field + " 不得为 null");
      }
      if (type == NotBlank.class) {
        throw new IllegalArgumentException(field + " 不得为空");
      }
      if (type == PositiveOrZero.class) {
        throw new IllegalArgumentException(field + " 不得为负: " + v.getInvalidValue());
      }
    }
    throw e;
  }
}
