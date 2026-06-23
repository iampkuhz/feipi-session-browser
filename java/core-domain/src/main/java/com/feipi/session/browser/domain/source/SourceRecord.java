package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.List;
import java.util.Objects;
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
 */
@DomainModel
public record SourceRecord(
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
    Optional<String> toolName) {

  /** 校验并防御性复制源记录字段。 */
  public SourceRecord {
    Objects.requireNonNull(locator, "locator 不得为 null");
    Objects.requireNonNull(eventType, "eventType 不得为 null");
    Objects.requireNonNull(callId, "callId 不得为 null");
    Objects.requireNonNull(model, "model 不得为 null");
    Objects.requireNonNull(timestamp, "timestamp 不得为 null");
    Objects.requireNonNull(turnId, "turnId 不得为 null");
    Objects.requireNonNull(usage, "usage 不得为 null");
    Objects.requireNonNull(toolCalls, "toolCalls 不得为 null");
    Objects.requireNonNull(toolUseId, "toolUseId 不得为 null");
    Objects.requireNonNull(toolName, "toolName 不得为 null");
    if (locator.isBlank()) {
      throw new IllegalArgumentException("locator 不得为空");
    }
    if (eventIndex < 0) {
      throw new IllegalArgumentException("eventIndex 不得为负数");
    }
    if (eventType.isBlank()) {
      eventType = "unknown";
    }
    toolCalls = List.copyOf(toolCalls);
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
        Optional.empty());
  }
}
