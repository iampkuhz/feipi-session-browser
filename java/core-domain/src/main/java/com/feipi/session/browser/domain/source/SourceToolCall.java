package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Objects;

/**
 * 源中性工具调用声明。
 *
 * <p>由 source adapter 在解析 provider 事件时提取，表示某条 assistant/source record 中声明的工具调用；不包含 provider 原始
 * payload。
 *
 * @param toolCallId 工具调用标识，来源于 provider 事件中的稳定 id
 * @param name 工具名称，来源于 provider 事件中的工具名字段
 */
@DomainModel
public record SourceToolCall(String toolCallId, String name) {

  /** 校验工具调用字段。 */
  public SourceToolCall {
    Objects.requireNonNull(toolCallId, "toolCallId 不得为 null");
    Objects.requireNonNull(name, "name 不得为 null");
    if (toolCallId.isBlank()) {
      throw new IllegalArgumentException("toolCallId 不得为空");
    }
    if (name.isBlank()) {
      throw new IllegalArgumentException("name 不得为空");
    }
  }
}
