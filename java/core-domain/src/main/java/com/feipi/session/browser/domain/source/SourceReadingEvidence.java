package com.feipi.session.browser.domain.source;

import java.util.Objects;

/**
 * 附属于同一物理事件的阅读证据，不增加源事件、消息或调用计数。
 *
 * @param kind 来源定义的证据类别
 * @param text 原始证据文本，不得输出到日志
 */
public record SourceReadingEvidence(String kind, String text) {
  /** 验证类型与正文，保持来源顺序由外部事件决定。 */
  public SourceReadingEvidence {
    Objects.requireNonNull(kind, "kind");
    Objects.requireNonNull(text, "text");
    if (kind.isBlank() || text.isBlank()) throw new IllegalArgumentException("阅读证据不得为空");
  }

  /** 日志仅保留类型和文本长度。 */
  @Override
  public String toString() {
    return "SourceReadingEvidence[kind=" + kind + ", length=" + text.length() + "]";
  }
}
