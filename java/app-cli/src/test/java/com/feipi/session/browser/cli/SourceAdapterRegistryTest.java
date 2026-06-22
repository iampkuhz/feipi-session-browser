package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceAdapterRegistry} 单元测试。
 *
 * <p>验证 sourceId 到 SourceAdapter 的映射正确性，以及未知 sourceId 的异常处理。
 */
@DisplayName("SourceAdapterRegistry 测试")
class SourceAdapterRegistryTest {

  @Test
  @DisplayName("CLAUDE_CODE 返回 ClaudeSourceAdapter")
  void claudeCodeUpperCase() {
    var adapter = SourceAdapterRegistry.forSourceId("CLAUDE_CODE");
    assertThat(adapter).isInstanceOf(ClaudeSourceAdapter.class);
  }

  @Test
  @DisplayName("claude_code 小写也返回 ClaudeSourceAdapter")
  void claudeCodeLowerCase() {
    var adapter = SourceAdapterRegistry.forSourceId("claude_code");
    assertThat(adapter).isInstanceOf(ClaudeSourceAdapter.class);
  }

  @Test
  @DisplayName("CODEX 返回 CodexSourceAdapter")
  void codexUpperCase() {
    var adapter = SourceAdapterRegistry.forSourceId("CODEX");
    assertThat(adapter).isInstanceOf(CodexSourceAdapter.class);
  }

  @Test
  @DisplayName("codex 小写也返回 CodexSourceAdapter")
  void codexLowerCase() {
    var adapter = SourceAdapterRegistry.forSourceId("codex");
    assertThat(adapter).isInstanceOf(CodexSourceAdapter.class);
  }

  @Test
  @DisplayName("QODER 返回 QoderSourceAdapter")
  void qoderUpperCase() {
    var adapter = SourceAdapterRegistry.forSourceId("QODER");
    assertThat(adapter).isInstanceOf(QoderSourceAdapter.class);
  }

  @Test
  @DisplayName("qoder 小写也返回 QoderSourceAdapter")
  void qoderLowerCase() {
    var adapter = SourceAdapterRegistry.forSourceId("qoder");
    assertThat(adapter).isInstanceOf(QoderSourceAdapter.class);
  }

  @Test
  @DisplayName("未知 sourceId 抛出 IllegalArgumentException")
  void unknownSourceIdThrows() {
    assertThatThrownBy(() -> SourceAdapterRegistry.forSourceId("UNKNOWN"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("Unknown source");
  }

  @Test
  @DisplayName("null sourceId 抛出 NullPointerException")
  void nullSourceIdThrows() {
    assertThatThrownBy(() -> SourceAdapterRegistry.forSourceId(null))
        .isInstanceOf(NullPointerException.class);
  }
}
