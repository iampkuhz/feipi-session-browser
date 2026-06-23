package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** {@link ScanConfig} 不变量验证测试。 */
class ScanConfigTest {

  @Test
  void rejectsEmptySourceEntries() {
    assertThatThrownBy(
            () ->
                new ScanConfig(
                    java.util.List.of(), java.nio.file.Path.of("/tmp"), java.util.Set.of(), 1))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("sourceEntries");
  }

  @Test
  void rejectsNegativeParallelism() {
    var entry = new ScanConfig.SourceEntry(new NoOpAdapter(), java.nio.file.Path.of("/tmp"));
    assertThatThrownBy(
            () ->
                new ScanConfig(
                    java.util.List.of(entry), java.nio.file.Path.of("/tmp"), java.util.Set.of(), 0))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("parseParallelism");
  }

  @Test
  void agentFilterEmptyMeansAllAllowed() {
    var entry = new ScanConfig.SourceEntry(new NoOpAdapter(), java.nio.file.Path.of("/tmp"));
    ScanConfig config =
        ScanConfig.defaults(java.util.List.of(entry), java.nio.file.Path.of("/tmp"));
    assertThat(config.isAgentAllowed("claude_code")).isTrue();
    assertThat(config.isAgentAllowed("codex")).isTrue();
  }

  @Test
  void agentFilterRestrictsToSpecifiedAgents() {
    var entry = new ScanConfig.SourceEntry(new NoOpAdapter(), java.nio.file.Path.of("/tmp"));
    ScanConfig config =
        new ScanConfig(
            java.util.List.of(entry),
            java.nio.file.Path.of("/tmp"),
            java.util.Set.of("claude_code"),
            1);
    assertThat(config.isAgentAllowed("claude_code")).isTrue();
    assertThat(config.isAgentAllowed("codex")).isFalse();
  }

  @Test
  void defaultsUsesSequentialParallelism() {
    var entry = new ScanConfig.SourceEntry(new NoOpAdapter(), java.nio.file.Path.of("/tmp"));
    ScanConfig config =
        ScanConfig.defaults(java.util.List.of(entry), java.nio.file.Path.of("/tmp"));
    assertThat(config.parseParallelism()).isEqualTo(1);
    assertThat(config.agentFilter()).isEmpty();
  }

  /** 最小 no-op 适配器，只用于构造测试。 */
  private static class NoOpAdapter implements com.feipi.session.browser.source.spi.SourceAdapter {
    @Override
    public com.feipi.session.browser.source.spi.SourceId sourceId() {
      return com.feipi.session.browser.source.spi.SourceId.CLAUDE_CODE;
    }

    @Override
    public com.feipi.session.browser.source.spi.BoundedStream<
            com.feipi.session.browser.source.spi.Candidate>
        discover(java.nio.file.Path rootPath) {
      return com.feipi.session.browser.source.spi.BoundedStream.of(
          java.util.List.of(), 0, java.util.Optional.empty());
    }

    @Override
    public com.feipi.session.browser.source.spi.SourceFingerprint fingerprint(
        java.nio.file.Path filePath) {
      throw new UnsupportedOperationException();
    }

    @Override
    public com.feipi.session.browser.source.spi.SourceResult parse(
        com.feipi.session.browser.source.spi.Candidate candidate,
        com.feipi.session.browser.source.spi.SourceAdapter.CancellationSignal cancellation) {
      throw new UnsupportedOperationException();
    }
  }
}
