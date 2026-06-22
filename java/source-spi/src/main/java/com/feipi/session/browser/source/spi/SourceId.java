package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 会话源适配器标识。
 *
 * <p>枚举当前支持的三种本地 agent 会话来源。每种来源对应独立的文件系统布局
 * 和解析逻辑，但通过统一 SPI 暴露给上层。
 *
 * <p>不可为 null；使用 {@link #fromValue(String)} 进行反序列化时，
 * 非法值将抛出 {@link IllegalArgumentException}。
 */
@DomainModel
public enum SourceId {

  /** Claude Code 会话源。 */
  @CoreField CLAUDE_CODE("claude_code"),

  /** Codex 会话源。 */
  @CoreField CODEX("codex"),

  /** Qoder 会话源。 */
  @CoreField QODER("qoder");

  private final String value;

  SourceId(String value) {
    this.value = value;
  }

  /**
   * 返回该源标识的字符串值，用于序列化和配置。
   *
   * @return 源标识字符串
   */
  public String value() {
    return value;
  }

  /**
   * 从字符串值解析对应的 {@code SourceId}。
   *
   * @param value 源标识字符串，必须与某个枚举常量的 {@link #value()} 匹配
   * @return 匹配的 {@code SourceId}
   * @throws IllegalArgumentException 当值不匹配任何已知源时
   * @throws NullPointerException 当值为 null 时
   */
  public static SourceId fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("SourceId value 不得为 null");
    }
    for (SourceId id : values()) {
      if (id.value.equals(value)) {
        return id;
      }
    }
    throw new IllegalArgumentException("未知 SourceId: " + value);
  }
}
