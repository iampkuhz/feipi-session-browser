package com.feipi.session.browser.index.store.sqlite.loader;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class NormalizedContentReaderTest {
  @TempDir Path directory;

  @Test
  void rejectsUnknownStorageFormat() throws Exception {
    Path data = directory.resolve("content.json");
    Files.writeString(data, "{\"storageFormat\":\"future\"}");
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(data))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("unsupported");
  }

  @Test
  void requiresCommittedMetadataForUnits() throws Exception {
    Path data = directory.resolve("content.json");
    Files.writeString(data, "{\"storageFormat\":\"session-content.units.v1\",\"units\":[]}");
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(data))
        .isInstanceOf(java.io.IOException.class);
  }

  @Test
  void replays10234CallsWithoutLegacyFlattening() throws Exception {
    Path data = fixture(10234, false);
    var content = NormalizedArtifactLoader.open(data);
    assertThat(content.header().totals().get("calls")).isEqualTo(10234L);
    for (int replay = 0; replay < 2; replay++) {
      int count = 0;
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          var unit = cursor.next();
          assertThat(unit.calls().getFirst().callIndex()).isEqualTo(++count);
          assertThat(unit.calls().getFirst().sourceUnits().getFirst().get("text"))
              .isEqualTo("synthetic text");
        }
      }
      assertThat(count).isEqualTo(10234);
    }
    assertThatThrownBy(content::toArtifact).isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void rejectsDuplicateGlobalCallsAndDamagedHash() throws Exception {
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(fixture(2, true)))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("duplicate");
    Path data = fixture(2, false);
    Files.writeString(data, " ", java.nio.file.StandardOpenOption.APPEND);
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(data))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("hash/size");
  }

  @Test
  void supportsLegacyBoundaryAndRejectsOversizeConversion() throws Exception {
    Path units = fixture(10000, false);
    assertThatThrownBy(() -> NormalizedArtifactLoader.load(units))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("open");
    assertThat(NormalizedArtifactLoader.open(units).toArtifact().calls()).hasSize(10000);
    Path legacy = directory.resolve("legacy.json");
    try (var writer = Files.newBufferedWriter(legacy)) {
      writer.write(
          "{\"schema_version\":\"session-detail.normalized.v3\",\"agent\":\"codex\",\"calls\":[");
      for (int n = 0; n < 10000; n++) {
        if (n > 0) writer.write(",");
        writer.write("{\"call_id\":\"legacy-" + n + "\",\"call_index\":" + (n + 1) + "}");
      }
      writer.write("]}");
    }
    assertThat(NormalizedArtifactLoader.load(legacy).calls()).hasSize(10000);
    var content = NormalizedArtifactLoader.open(fixture(10001, false));
    assertThatThrownBy(content::toArtifact).isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void rejectsTruncationTotalsAndSequenceGaps() throws Exception {
    Path data = fixture(2, false);
    String original = Files.readString(data);
    Files.writeString(data, original.substring(0, original.length() - 2));
    commitMetadata(data);
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(data))
        .isInstanceOf(java.io.IOException.class);
    Files.writeString(data, original.replace("\"calls\":2", "\"calls\":3"));
    commitMetadata(data);
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(data))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("totals");
    Files.writeString(
        data,
        original.replace(
            "\"unitIndex\":0",
            "\"sourceUnitSequences\":[{\"name\":\"s\",\"offset\":1,\"keys\":[\"unknown\"]}],\"unitIndex\":0"));
    commitMetadata(data);
    assertThatThrownBy(() -> NormalizedArtifactLoader.open(data))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("sequence gap");
  }

  @Test
  void closesEarlyAndReopensAtFirstUnit() throws Exception {
    Path data = fixture(2, false);
    var content = NormalizedArtifactLoader.open(data);
    try (var cursor = content.openCursor()) {
      assertThat(cursor.next().unitIndex()).isZero();
    }
    try (var cursor = content.openCursor()) {
      assertThat(cursor.next().unitIndex()).isZero();
    }
    Files.writeString(data, " ", java.nio.file.StandardOpenOption.APPEND);
    assertThatThrownBy(content::openCursor).isInstanceOf(java.io.IOException.class);
  }

  @Test
  void preservesLegacyDiagnosticsCatalogSequencesAndCallProvenance() {
    var entry =
        java.util.Map.ofEntries(
            java.util.Map.entry("unitKey", "u"),
            java.util.Map.entry("originPath", "synthetic.jsonl"),
            java.util.Map.entry("canonicalSourceLocator", "line:1"),
            java.util.Map.entry("unitType", "message"),
            java.util.Map.entry("candidate", ""),
            java.util.Map.entry("direction", "request"),
            java.util.Map.entry("byteRange", java.util.Map.of("start", 0, "end", 10)),
            java.util.Map.entry("contentHash", "synthetic-hash"),
            java.util.Map.entry("text", "source text"));
    var root =
        java.util.Map.<String, Object>of(
            "agent",
            "codex",
            "calls",
            java.util.List.of(
                java.util.Map.of(
                    "call_id",
                    "c",
                    "usage_source",
                    java.util.Map.of("kind", "observed"),
                    "attribution_candidates",
                    java.util.Map.of("bucket", "request"),
                    "source_unit_ref_ranges",
                    java.util.List.of(java.util.Map.of("refs", java.util.List.of("u"))))),
            "diagnostics",
            java.util.List.of(java.util.Map.of("code", "synthetic")),
            "source_unit_catalog",
            java.util.Map.of("u", entry),
            "source_unit_sequences",
            java.util.Map.of("s", java.util.List.of("u")));
    var artifact = NormalizedArtifactLoader.fromMap(root);
    assertThat(artifact.diagnostics().getFirst().get("code")).isEqualTo("synthetic");
    assertThat(artifact.sourceUnitCatalog().get("u").text()).contains("source text");
    assertThat(artifact.sourceUnitSequences().get("s")).containsExactly("u");
    assertThat(artifact.calls().getFirst().usageSource()).containsEntry("kind", "observed");
    assertThat(artifact.calls().getFirst().sourceUnitRefRanges().getFirst().refs())
        .containsExactly("u");
    assertThat(artifact.calls().getFirst().attributionCandidates())
        .containsEntry("bucket", "request");
  }

  @Test
  void boundedConsumerRunsUnder64MiBWithTenfoldTextGrowth() throws Exception {
    long small = heapProbe(fixture(10, false, "x".repeat(700000)));
    long large = heapProbe(fixture(100, false, "x".repeat(700000)));
    assertThat(large - small).isLessThan(8L * 1024 * 1024);
    System.out.println("READER_HEAP_64M small=" + small + " large=" + large);
  }

  private long heapProbe(Path path) throws Exception {
    var entries = new java.util.LinkedHashSet<String>();
    entries.add(System.getProperty("java.class.path"));
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof java.net.URLClassLoader urls) {
        for (var url : urls.getURLs()) entries.add(Path.of(url.toURI()).toString());
      }
    }
    Path log = directory.resolve("heap-" + Files.size(path) + ".log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-Xmx64m",
                "-cp",
                String.join(java.io.File.pathSeparator, entries),
                HeapProbe.class.getName(),
                path.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    assertThat(process.waitFor(90, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
    assertThat(process.exitValue()).withFailMessage(Files.readString(log)).isZero();
    try (var lines = Files.lines(log)) {
      return lines
          .filter(line -> line.startsWith("LIVE_HEAP="))
          .mapToLong(line -> Long.parseLong(line.substring(10)))
          .findFirst()
          .orElseThrow();
    }
  }

  /** 独立的有界消费者，不在内容单元之间保留测试正文。 */
  public static final class HeapProbe {
    /** 在独立进程中以固定堆预算运行。 */
    public static void main(String[] args) throws Exception {
      var content = NormalizedArtifactLoader.open(Path.of(args[0]));
      long peak = 0;
      for (int replay = 0; replay < 2; replay++) {
        long count = 0;
        try (var cursor = content.openCursor()) {
          while (cursor.hasNext()) {
            if (cursor.next().calls().getFirst().callIndex() != ++count)
              throw new AssertionError("unexpected identity");
            System.gc();
            peak =
                Math.max(
                    peak,
                    java.lang.management.ManagementFactory.getMemoryMXBean()
                        .getHeapMemoryUsage()
                        .getUsed());
          }
        }
        if (count != content.header().totals().get("calls"))
          throw new AssertionError("missing calls");
      }
      System.out.println("LIVE_HEAP=" + peak);
    }
  }

  @Test
  void loadRejectsSmallUnitsContentAndPointsToOpen() throws Exception {
    Path data = fixture(2, false);
    assertThatThrownBy(() -> NormalizedArtifactLoader.load(data))
        .isInstanceOf(java.io.IOException.class)
        .hasMessageContaining("open");
    var content = NormalizedArtifactLoader.open(data);
    for (int replay = 0; replay < 2; replay++) {
      int count = 0;
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) count += cursor.next().calls().size();
      }
      assertThat(count).isEqualTo(2);
    }
  }

  private Path fixture(int count, boolean duplicate) throws Exception {
    return fixture(count, duplicate, "synthetic text");
  }

  private Path fixture(int count, boolean duplicate, String text) throws Exception {
    Path data = directory.resolve("content.json");
    try (var writer = Files.newBufferedWriter(data)) {
      writer.write(
          "{\"storageFormat\":\"session-content.units.v1\",\"header\":{"
              + "\"schemaVersion\":\"session-detail.normalized.v3\",\"agent\":\"codex\","
              + "\"session\":{\"session_key\":\"codex:synthetic\"},\"totals\":{\"calls\":"
              + count
              + ",\"toolExecutions\":0,\"diagnostics\":0,\"sourceFiles\":0,"
              + "\"sourceUnitCatalog\":0,\"sourceUnitSequenceEntries\":0}},\"units\":[");
      for (int n = 0; n < count; n++) {
        if (n != 0) writer.write(",");
        writer.write(
            "{\"unitIndex\":"
                + n
                + ",\"calls\":[{\"call_id\":\"c"
                + (duplicate ? 0 : n)
                + "\",\"call_index\":"
                + (n + 1)
                + ",\"source_units\":[{\"text\":\""
                + text
                + "\"}]}]}");
      }
      writer.write("]}");
    }
    commitMetadata(data);
    return data;
  }

  private void commitMetadata(Path data) throws Exception {
    var digest = java.security.MessageDigest.getInstance("SHA-256");
    try (var input = Files.newInputStream(data)) {
      byte[] buffer = new byte[8192];
      int n;
      while ((n = input.read(buffer)) != -1) digest.update(buffer, 0, n);
    }
    Files.writeString(
        directory.resolve("content.meta.json"),
        "{\"contentHash\":\""
            + java.util.HexFormat.of().formatHex(digest.digest())
            + "\",\"contentSize\":"
            + Files.size(data)
            + "}");
  }
}
