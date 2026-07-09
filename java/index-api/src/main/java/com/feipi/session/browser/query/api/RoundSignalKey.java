package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 轮次级信号注册键枚举。
 *
 * <p>定义轮次级信号检测器支持的所有信号类型键。与 Python 端 {@code ROUND_SIGNAL_DEFINITIONS} 注册表的键对应。 值为稳定外部协议契约。
 */
@RequiredArgsConstructor
public enum RoundSignalKey {
  /** 轮次包含失败的工具调用。 */
  FAILED_TOOL("failed-tool"),

  /** 轮次包含 LLM 错误。 */
  LLM_ERROR("llm-error"),

  /** 轮次包含长时间工具调用。 */
  LONG_TOOL("long-tool"),

  /** 轮次包含工具调用爆发。 */
  TOOL_BURST("tool-burst"),

  /** 轮次缓存写入过高。 */
  HIGH_WRITE("high-write"),

  /** 轮次输入 token 过高。 */
  LARGE_INPUT("large-input");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 信号键字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static RoundSignalKey fromValue(String value) {
    for (RoundSignalKey key : values()) {
      if (key.value.equals(value)) {
        return key;
      }
    }
    throw new IllegalArgumentException("无法识别的轮次信号键: " + value);
  }
}
