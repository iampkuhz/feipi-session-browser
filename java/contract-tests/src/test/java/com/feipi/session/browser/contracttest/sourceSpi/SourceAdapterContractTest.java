package com.feipi.session.browser.contracttest.sourceSpi;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.FakeSourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceOutcome;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceAdapter} SPI 契约测试。
 *
 * <p>使用 {@link FakeSourceAdapter} 验证 SPI 接口的完整行为契约。
 * 覆盖三来源中性、确定性排序、路径安全检查和取消信号。
 */
@DisplayName("Source SPI — SourceAdapter SPI 契约")
class SourceAdapterContractTest {

  @Test
  @DisplayName("适配器报告正确的 sourceId")
  void adapterReportsCorrectSourceId() {
    FakeSourceAdapter adapter = new FakeSourceAdapter(SourceId.CLAUDE_CODE, List.of());
    assertThat(adapter.sourceId()).isEqualTo(SourceId.CLAUDE_CODE);
  }

  @Test
  @DisplayName("三来源适配器均符合 SPI")
  void allThreeSourcesConformToSpi() {
    for (SourceId id : SourceId.values()) {
      SourceAdapter adapter = new FakeSourceAdapter(id, List.of());
      assertThat(adapter.sourceId()).isEqualTo(id);
      assertThat(adapter.discover(Path.of("/test")).isEmpty()).isTrue();
    }
  }

  @Test
  @DisplayName("discover 返回按路径排序的确定性结果")
  void discoverReturnsDeterministicOrder() {
    Candidate c1 = FakeSourceAdapter.testCandidate("/z.jsonl", "s1", SourceId.CODEX);
    Candidate c2 = FakeSourceAdapter.testCandidate("/a.jsonl", "s2", SourceId.CODEX);
    Candidate c3 = FakeSourceAdapter.testCandidate("/m.jsonl", "s3", SourceId.CODEX);

    FakeSourceAdapter adapter = new FakeSourceAdapter(SourceId.CODEX, List.of(c1, c2, c3));
    BoundedStream<Candidate> stream = adapter.discover(Path.of("/data"));

    assertThat(stream.orderedItems())
        .extracting(c -> c.fingerprint().path())
        .containsExactly("/a.jsonl", "/m.jsonl", "/z.jsonl");
  }

  @Test
  @DisplayName("fingerprint 包含内容哈希")
  void fingerprintIncludesContentHash() {
    FakeSourceAdapter adapter = new FakeSourceAdapter(SourceId.QODER, List.of());
    SourceFingerprint fp = adapter.fingerprint(Path.of("/data/test.jsonl"));
    assertThat(fp.sourceId()).isEqualTo(SourceId.QODER);
    assertThat(fp.contentHash()).isPresent();
  }

  @Test
  @DisplayName("checkRoot 返回安全源根")
  void checkRootReturnsSafeRoot() {
    FakeSourceAdapter adapter = new FakeSourceAdapter(SourceId.CLAUDE_CODE, List.of());
    SourceRoot root = adapter.checkRoot(Path.of("/data/sessions"));
    assertThat(root.isSafe()).isTrue();
  }

  @Test
  @DisplayName("parse 成功状态返回 Success 结果")
  void parseSuccessOutcome() {
    Candidate c = FakeSourceAdapter.testCandidate("/test.jsonl", "s1", SourceId.CODEX);
    FakeSourceAdapter adapter =
        new FakeSourceAdapter(SourceId.CODEX, List.of(c), SourceOutcome.SUCCESS);
    SourceResult result = adapter.parse(c, Optional.empty());
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
  }

  @Test
  @DisplayName("parse 可重试状态返回 RetryableIncomplete 结果")
  void parseRetryableOutcome() {
    Candidate c = FakeSourceAdapter.testCandidate("/test.jsonl", "s1", SourceId.CODEX);
    FakeSourceAdapter adapter =
        new FakeSourceAdapter(SourceId.CODEX, List.of(c), SourceOutcome.RETRYABLE_INCOMPLETE);
    SourceResult result = adapter.parse(c, Optional.empty());
    assertThat(result).isInstanceOf(SourceResult.RetryableIncomplete.class);
    assertThat(result.outcome()).isEqualTo(SourceOutcome.RETRYABLE_INCOMPLETE);
  }

  @Test
  @DisplayName("parse 跳过状态返回 Skipped 结果")
  void parseSkippedOutcome() {
    Candidate c = FakeSourceAdapter.testCandidate("/test.jsonl", "s1", SourceId.CODEX);
    FakeSourceAdapter adapter =
        new FakeSourceAdapter(SourceId.CODEX, List.of(c), SourceOutcome.SKIPPED);
    SourceResult result = adapter.parse(c, Optional.empty());
    assertThat(result).isInstanceOf(SourceResult.Skipped.class);
  }

  @Test
  @DisplayName("parse 致命状态返回 Fatal 结果")
  void parseFatalOutcome() {
    Candidate c = FakeSourceAdapter.testCandidate("/test.jsonl", "s1", SourceId.CODEX);
    FakeSourceAdapter adapter =
        new FakeSourceAdapter(SourceId.CODEX, List.of(c), SourceOutcome.FATAL);
    SourceResult result = adapter.parse(c, Optional.empty());
    assertThat(result).isInstanceOf(SourceResult.Fatal.class);
    assertThat(result.outcome()).isEqualTo(SourceOutcome.FATAL);
  }

  @Test
  @DisplayName("取消信号导致 Skipped 结果")
  void cancellationLeadsToSkipped() {
    Candidate c = FakeSourceAdapter.testCandidate("/test.jsonl", "s1", SourceId.CODEX);
    FakeSourceAdapter adapter =
        new FakeSourceAdapter(SourceId.CODEX, List.of(c), SourceOutcome.SUCCESS);
    SourceAdapter.CancellationSignal cancelled = () -> true;
    SourceResult result = adapter.parse(c, Optional.of(cancelled));
    assertThat(result).isInstanceOf(SourceResult.Skipped.class);
  }

  @Test
  @DisplayName("未取消时正常执行")
  void notCancelledProceedsNormally() {
    Candidate c = FakeSourceAdapter.testCandidate("/test.jsonl", "s1", SourceId.CODEX);
    FakeSourceAdapter adapter =
        new FakeSourceAdapter(SourceId.CODEX, List.of(c), SourceOutcome.SUCCESS);
    SourceAdapter.CancellationSignal notCancelled = () -> false;
    SourceResult result = adapter.parse(c, Optional.of(notCancelled));
    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
  }

  @Test
  @DisplayName("SPI 接口不引用 Jackson JsonNode 类型")
  void spiDoesNotLeakJacksonTypes() {
    // 验证 SourceAdapter 方法签名不包含 Jackson 类型
    for (var method : SourceAdapter.class.getDeclaredMethods()) {
      assertThat(method.getReturnType().getName())
          .as("返回类型 %s 不得为 Jackson 类型", method.getReturnType().getName())
          .doesNotContain("com.fasterxml.jackson");
      for (Class<?> paramType : method.getParameterTypes()) {
        assertThat(paramType.getName())
            .as("参数类型 %s 不得为 Jackson 类型", paramType.getName())
            .doesNotContain("com.fasterxml.jackson");
      }
    }
  }

  @Test
  @DisplayName("SPI 结果类型不引用 JsonNode")
  void resultTypesDoNotLeakJsonNode() {
    for (Class<?> type :
        List.of(
            SourceResult.class,
            SourceResult.Success.class,
            SourceResult.RetryableIncomplete.class,
            SourceResult.Skipped.class,
            SourceResult.Fatal.class,
            Candidate.class,
            SourceFingerprint.class)) {
      for (var method : type.getDeclaredMethods()) {
        assertThat(method.getReturnType().getName())
            .doesNotContain("JsonNode")
            .doesNotContain("com.fasterxml.jackson");
      }
    }
  }
}
