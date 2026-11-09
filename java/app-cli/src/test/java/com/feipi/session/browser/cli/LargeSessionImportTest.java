package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.SequenceInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

/** 使用真实 Claude 解析器验证最大默认文件在有界服务堆内可完成完整分析。 */
class LargeSessionImportTest {
  private static final long MAX_BYTES = 200L * 1024 * 1024;
  private static final int RECORDS = 211;

  @Test
  @Timeout(value = 300, unit = TimeUnit.SECONDS)
  void importsTwoHundredMebibytesThroughTheRealSourceAdapter() throws Exception {
    String prefix =
        "{\"type\":\"assistant\",\"sessionId\":\"synthetic-large\",\"message\":{\"role\":\"assistant\",\"content\":\"";
    String suffix = "\"}}\n";
    int lineBytes = Math.toIntExact(MAX_BYTES / RECORDS);
    int lastLineBytes = Math.toIntExact(MAX_BYTES - (long) lineBytes * (RECORDS - 1));
    byte[] line = syntheticLine(prefix, suffix, lineBytes);
    byte[] lastLine = syntheticLine(prefix, suffix, lastLineBytes);
    var parts = new ArrayList<InputStream>(RECORDS);
    for (int index = 0; index < RECORDS; index++) {
      parts.add(new ByteArrayInputStream(index == RECORDS - 1 ? lastLine : line));
    }

    var adapter = SourceAdapterRegistry.forSourceId("claude_code");
    try (var service = new IsolatedSessionImportService(ignored -> adapter)) {
      var analysis =
          service.create(
              new SequenceInputStream(Collections.enumeration(parts)),
              "synthetic-200mib.jsonl",
              NormalizedAgent.CLAUDE_CODE);

      assertThat(analysis.metadata().sizeBytes()).isEqualTo(MAX_BYTES);
      assertThat(analysis.artifact().calls()).hasSize(RECORDS);
      int largestText =
          analysis.artifact().calls().getFirst().sourceUnits().stream()
              .flatMap(unit -> unit.values().stream())
              .filter(String.class::isInstance)
              .map(String.class::cast)
              .mapToInt(String::length)
              .max()
              .orElse(0);
      assertThat(largestText).isGreaterThan(900_000);
    }
  }

  private static byte[] syntheticLine(String prefix, String suffix, int bytes) {
    int contentLength = bytes - prefix.length() - suffix.length();
    if (contentLength < 0 || contentLength > 1_000_000) {
      throw new IllegalArgumentException("synthetic line exceeds import validation limits");
    }
    return (prefix + "x".repeat(contentLength) + suffix).getBytes(StandardCharsets.UTF_8);
  }
}
