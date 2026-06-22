package com.feipi.session.browser.cli;

import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter;

/**
 * 根据 sourceId 字符串返回对应的 {@link SourceAdapter} 实例。
 *
 * <p>支持的 sourceId（不区分大小写）：
 *
 * <ul>
 *   <li>{@code CLAUDE_CODE} / {@code claude_code} — Claude Code 适配器
 *   <li>{@code CODEX} / {@code codex} — Codex 适配器
 *   <li>{@code QODER} / {@code qoder} — Qoder 适配器
 * </ul>
 */
final class SourceAdapterRegistry {

  private SourceAdapterRegistry() {}

  /**
   * 根据源标识返回对应的 {@link SourceAdapter}。
   *
   * <p>匹配时不区分大小写。未知 sourceId 抛出异常。
   *
   * @param sourceId 源标识字符串
   * @return 对应的 SourceAdapter 实例
   * @throws IllegalArgumentException 当 sourceId 未知时
   * @throws NullPointerException 当 sourceId 为 null 时
   */
  static SourceAdapter forSourceId(String sourceId) {
    if (sourceId == null) {
      throw new NullPointerException("sourceId 不得为 null");
    }
    return switch (sourceId.toUpperCase()) {
      case "CLAUDE_CODE" -> new ClaudeSourceAdapter();
      case "CODEX" -> new CodexSourceAdapter();
      case "QODER" -> new QoderSourceAdapter();
      default -> throw new IllegalArgumentException("Unknown source: " + sourceId);
    };
  }
}
