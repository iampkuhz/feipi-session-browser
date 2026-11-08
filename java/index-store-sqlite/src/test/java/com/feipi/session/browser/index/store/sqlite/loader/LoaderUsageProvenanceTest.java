package com.feipi.session.browser.index.store.sqlite.loader;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 调用来源在磁盘读取时保留，不从用量数值或会话汇总补齐。 */
class LoaderUsageProvenanceTest {
  @TempDir Path directory;

  @Test
  void diskLoaderPreservesReportedZeroAndMissingProvenance() throws Exception {
    Path file = directory.resolve("content.json");
    Files.writeString(
        file,
        """
          {"agent":"codex","session":{"freshInputTokenPrecision":"provider_reported"},
           "calls":[{"call_id":"reported-zero","call_index":1,"usage":{"fresh":0},
             "usage_source":{"freshInputTokenPrecision":"provider_reported","outputTokenPrecision":"unavailable"}},
            {"call_id":"unavailable","call_index":2,"usage":{"fresh":10,"total":10}}]}
          """);
    var calls = NormalizedArtifactLoader.load(file).calls();
    assertThat(calls).hasSize(2);
    assertThat(calls.get(0).usageSource())
        .hasSize(2)
        .containsEntry("freshInputTokenPrecision", "provider_reported")
        .containsEntry("outputTokenPrecision", "unavailable");
    assertThat(calls.get(0).usage().fresh()).isZero();
    assertThat(calls.get(1).usageSource()).isEmpty();
    assertThat(calls.get(1).usage().fresh()).isEqualTo(10);
  }
}
