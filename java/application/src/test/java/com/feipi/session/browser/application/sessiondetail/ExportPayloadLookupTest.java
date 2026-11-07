package com.feipi.session.browser.application.sessiondetail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 私有导出索引在成功、损坏及构造异常时都必须清理。 */
class ExportPayloadLookupTest {
  @TempDir Path directory;

  @Test
  void privateFileIsRandomReadableAndRemovedAfterClose() throws Exception {
    try (var lookup = ExportPayloadLookup.build(content(), directory)) {
      Path file = onlyFile();
      assertThat(Files.getPosixFilePermissions(file))
          .isEqualTo(PosixFilePermissions.fromString("rw-------"));
      assertThat(lookup.input("tool").orElseThrow().input()).contains("synthetic-input");
      assertThat(lookup.result("tool")).contains("synthetic-result");
    }
    assertEmpty();
  }

  @Test
  void truncatedLookupFailsRatherThanReturningPartialPayloadAndStillCleansUp() throws Exception {
    try (var lookup = ExportPayloadLookup.build(content(), directory)) {
      Files.write(onlyFile(), new byte[0]);
      assertThatThrownBy(() -> lookup.input("tool")).isInstanceOf(IOException.class);
    }
    assertEmpty();
  }

  @Test
  void cursorConstructionFailureRemovesLookupFile() {
    NormalizedSessionContent broken =
        new NormalizedSessionContent() {
          public NormalizedContentHeader header() {
            return content().header();
          }

          public ContentCursor openCursor() throws IOException {
            throw new IOException("synthetic cursor failure");
          }
        };
    assertThatThrownBy(() -> ExportPayloadLookup.build(broken, directory))
        .isInstanceOf(IOException.class)
        .hasMessage("synthetic cursor failure");
    assertEmpty();
  }

  @Test
  void generatedCatalogAndToolGrowthCompletesWithFixed64MiBHeap() throws Exception {
    var entries = new java.util.LinkedHashSet<String>();
    entries.add(System.getProperty("java.class.path"));
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof java.net.URLClassLoader urls) {
        for (var url : urls.getURLs()) entries.add(Path.of(url.toURI()).toString());
      }
    }
    Path log = directory.resolve("lookup-64m.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-Xmx64m",
                "-cp",
                String.join(java.io.File.pathSeparator, entries),
                GrowthProbe.class.getName(),
                directory.resolve("lookup").toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean done = process.waitFor(120, java.util.concurrent.TimeUnit.SECONDS);
    if (!done) process.destroyForcibly();
    assertThat(done).withFailMessage("64MiB lookup child exceeded test deadline").isTrue();
    assertThat(process.exitValue()).withFailMessage(Files.readString(log)).isZero();
    assertThat(Files.readString(log))
        .contains(
            "LOOKUP_GROWTH_OK items=40 passes=2 units=80",
            "LOOKUP_GROWTH_OK items=80 passes=2 units=160",
            "heapMax=67108864");
    System.out.print(Files.readString(log));
  }

  /** 子进程按需生成当前单元，累计正文超过固定堆；不预先构造正文列表。 */
  public static final class GrowthProbe {
    private static final int BODY_BYTES = 900 * 1024;

    /** 独立固定堆校验两种规模、重复重放、首尾全文摘要和文件清理。 */
    public static void main(String[] args) throws Exception {
      Path directory = Files.createDirectory(Path.of(args[0]));
      for (int count : new int[] {40, 80}) {
        var content = new GeneratedContent(count);
        for (int replay = 0; replay < 2; replay++) {
          try (var lookup = ExportPayloadLookup.build(content, directory)) {
            try (var files = Files.list(directory)) {
              Path file = files.findFirst().orElseThrow();
              long bytes = Files.size(file);
              if (bytes < (long) count * BODY_BYTES * 3
                  || bytes <= Runtime.getRuntime().maxMemory()) {
                throw new AssertionError("fixture does not exceed fixed heap: " + bytes);
              }
            }
            for (int index : new int[] {0, count - 1}) {
              verify(lookup.catalogText("body-" + index, false), text("body", index));
              verify(lookup.input("tool-" + index).orElseThrow().input(), text("input", index));
              verify(lookup.result("tool-" + index).orElseThrow(), text("result", index));
            }
          }
          try (var files = Files.list(directory)) {
            if (files.findAny().isPresent()) throw new AssertionError("lookup file survived close");
          }
        }
        if (content.opens != 2 || content.reads != 2 * count)
          throw new AssertionError("unexpected replay");
        System.out.println(
            "LOOKUP_GROWTH_OK items="
                + count
                + " passes="
                + content.opens
                + " units="
                + content.reads
                + " heapMax="
                + Runtime.getRuntime().maxMemory());
      }
    }

    private static String text(String kind, int index) {
      String prefix = kind + "-" + index + ":";
      return prefix + "x".repeat(BODY_BYTES - prefix.length());
    }

    private static void verify(String actual, String expected) throws Exception {
      var digest = java.security.MessageDigest.getInstance("SHA-256");
      byte[] actualHash = digest.digest(actual.getBytes(java.nio.charset.StandardCharsets.UTF_8));
      byte[] expectedHash =
          digest.digest(expected.getBytes(java.nio.charset.StandardCharsets.UTF_8));
      if (actual.length() != BODY_BYTES || !java.util.Arrays.equals(actualHash, expectedHash)) {
        throw new AssertionError("full payload hash mismatch");
      }
    }

    private static SourceUnitCatalogEntry entry(
        String id, String type, boolean request, String text, Object payload) {
      return new SourceUnitCatalogEntry(
          id,
          "synthetic.jsonl",
          "synthetic:" + id,
          type,
          "synthetic",
          request ? SourceUnitDirection.REQUEST : SourceUnitDirection.RESPONSE,
          0,
          0,
          new ByteRange(0, 1),
          "synthetic-hash",
          Optional.empty(),
          Optional.empty(),
          50,
          Optional.empty(),
          Optional.of(text),
          payload,
          Optional.empty(),
          Optional.empty(),
          List.of());
    }

    /** 只保留规模和计数，next时才分配本单元的三项正文。 */
    private static final class GeneratedContent implements NormalizedSessionContent {
      private final int count;
      private int opens;
      private int reads;

      private GeneratedContent(int count) {
        this.count = count;
      }

      public NormalizedContentHeader header() {
        return new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                0L,
                "toolExecutions",
                0L,
                "diagnostics",
                0L,
                "sourceFiles",
                0L,
                "sourceUnitCatalog",
                3L * count,
                "sourceUnitSequenceEntries",
                0L));
      }

      public ContentCursor openCursor() {
        opens++;
        return new ContentCursor() {
          private int index;

          public boolean hasNext() {
            return index < count;
          }

          public NormalizedContentUnit next() {
            int current = index++;
            reads++;
            var body = entry("body-" + current, "text", false, text("body", current), Map.of());
            var input =
                entry(
                    "input-" + current,
                    "tool_use",
                    false,
                    "",
                    Map.of(
                        "type",
                        "tool_use",
                        "id",
                        "tool-" + current,
                        "name",
                        "shell",
                        "input",
                        text("input", current)));
            var result =
                entry(
                    "result-" + current,
                    "tool_result",
                    true,
                    text("result", current),
                    Map.of("tool_call_id", "tool-" + current));
            return new NormalizedContentUnit(
                current,
                List.of(),
                List.of(),
                List.of(),
                List.of(),
                Map.of(
                    "body-" + current,
                    body,
                    "input-" + current,
                    input,
                    "result-" + current,
                    result),
                List.of());
          }

          public void close() {}
        };
      }
    }
  }

  private Path onlyFile() throws IOException {
    try (var files = Files.list(directory)) {
      var paths = files.toList();
      assertThat(paths).hasSize(1);
      return paths.getFirst();
    }
  }

  private void assertEmpty() {
    try (var files = Files.list(directory)) {
      assertThat(files.toList()).isEmpty();
    } catch (IOException failure) {
      throw new java.io.UncheckedIOException(failure);
    }
  }

  private static NormalizedSessionContent content() {
    var call =
        new NormalizedCall(
            "call",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("turn"),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            new NormalizedCallResponse(List.of("tool")),
            List.of(),
            List.of(
                Map.of(
                    "role",
                    "assistant",
                    "type",
                    "tool_use",
                    "id",
                    "tool",
                    "name",
                    "shell",
                    "input",
                    "synthetic-input"),
                Map.of(
                    "role",
                    "user",
                    "type",
                    "tool_result",
                    "tool_call_id",
                    "tool",
                    "content",
                    "synthetic-result")),
            Map.of(),
            Map.of());
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                1L,
                "toolExecutions",
                0L,
                "diagnostics",
                0L,
                "sourceFiles",
                0L,
                "sourceUnitCatalog",
                0L,
                "sourceUnitSequenceEntries",
                0L)),
        List.of(),
        List.of(call),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
