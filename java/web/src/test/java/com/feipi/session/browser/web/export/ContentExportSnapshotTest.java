package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/** 使用合成内容验证完整重放导出，确保超出旧制品与页面上限的尾部内容仍被保留。 */
public class ContentExportSnapshotTest {
  @Test
  void completeSnapshotIncludesTailAndExactIdentityAndCounts() throws Exception {
    var bytes = new java.io.ByteArrayOutputStream();
    try (var snapshot =
        ContentExportSnapshot.html(content(), 1, PayloadVisibility.STANDARD, 50L * 1024 * 1024)) {
      snapshot.copyTo(bytes);
    }
    String html = bytes.toString(java.nio.charset.StandardCharsets.UTF_8);
    assertThat(html)
        .contains("synthetic response 10234", "synthetic-10234", "10234", "20468")
        .contains("[REDACTED]", "[LOCAL_PATH]", "&lt;unsafe&gt;")
        .doesNotContain("synthetic-secret", "/Users/alice", "fetch(", "<script src", "<link href");
  }

  @Test
  void sizeLimitIsAllOrErrorRatherThanPartialSuccess() {
    assertThatThrownBy(
            () -> ContentExportSnapshot.html(content(), 1, PayloadVisibility.STANDARD, 1024))
        .isInstanceOf(ContentExportSnapshot.LimitExceededException.class);
  }

  @Test
  void actualFiftyMiBLimitAndCompletedFileCleanupAreEnforced() throws Exception {
    long max = 50L * 1024 * 1024;
    assertThatThrownBy(
            () ->
                ContentExportSnapshot.create(
                    max,
                    output -> {
                      byte[] block = new byte[8192];
                      for (long count = 0; count < max; count += block.length) output.write(block);
                      output.write(1);
                    }))
        .isInstanceOf(ContentExportSnapshot.LimitExceededException.class);
    var snapshot = ContentExportSnapshot.create(64, output -> output.write(42));
    assertThat(snapshot.size()).isEqualTo(1);
    snapshot.close();
    assertThatThrownBy(() -> snapshot.copyTo(java.io.OutputStream.nullOutputStream()))
        .isInstanceOf(java.nio.file.NoSuchFileException.class);
  }

  @Test
  void toolInputAndResultAcrossIndependentUnitsRemainInOfflineSnapshot() throws Exception {
    var first =
        call(
            1,
            List.of(
                Map.of(
                    "role",
                    "assistant",
                    "type",
                    "tool_use",
                    "id",
                    "synthetic-tool",
                    "name",
                    "shell",
                    "input",
                    Map.of("command", "echo synthetic-tool-input"))));
    var last =
        call(
            2,
            List.of(
                Map.of(
                    "role",
                    "user",
                    "type",
                    "tool_result",
                    "tool_call_id",
                    "synthetic-tool",
                    "content",
                    "synthetic-tool-result token=synthetic-secret")));
    var tool =
        new com.feipi.session.browser.domain.normalized.NormalizedToolExecution(
            "synthetic-tool",
            "shell",
            CallScope.MAIN,
            "synthetic-1",
            Optional.of("synthetic-2"),
            Optional.empty(),
            Optional.of(0),
            0,
            List.of(),
            Optional.empty());
    var units =
        List.of(
            new com.feipi.session.browser.domain.normalized.NormalizedContentUnit(
                0, List.of(), List.of(first), List.of(), List.of(), Map.of(), List.of()),
            new com.feipi.session.browser.domain.normalized.NormalizedContentUnit(
                1, List.of(), List.of(last), List.of(), List.of(), Map.of(), List.of()),
            new com.feipi.session.browser.domain.normalized.NormalizedContentUnit(
                2, List.of(), List.of(), List.of(tool), List.of(), Map.of(), List.of()));
    NormalizedSessionContent content =
        new NormalizedSessionContent() {
          public NormalizedContentHeader header() {
            return new NormalizedContentHeader(
                NormalizedConstants.SCHEMA_VERSION,
                NormalizedAgent.CODEX,
                new NormalizedSessionMetadata(Map.of()),
                Map.of(
                    "calls",
                    2L,
                    "toolExecutions",
                    1L,
                    "diagnostics",
                    0L,
                    "sourceFiles",
                    0L,
                    "sourceUnitCatalog",
                    0L,
                    "sourceUnitSequenceEntries",
                    0L));
          }

          public ContentCursor openCursor() {
            var iterator = units.iterator();
            return new ContentCursor() {
              public boolean hasNext() {
                return iterator.hasNext();
              }

              public com.feipi.session.browser.domain.normalized.NormalizedContentUnit next() {
                return iterator.next();
              }

              public void close() {}
            };
          }
        };
    var bytes = new java.io.ByteArrayOutputStream();
    try (var snapshot =
        ContentExportSnapshot.html(content, 1, PayloadVisibility.STANDARD, 1024 * 1024)) {
      snapshot.copyTo(bytes);
    }
    assertThat(bytes.toString(java.nio.charset.StandardCharsets.UTF_8))
        .contains("synthetic-tool", "synthetic-tool-input", "synthetic-tool-result", "[REDACTED]")
        .doesNotContain("synthetic-secret");
  }

  public static NormalizedSessionContent content() {
    var calls = IntStream.rangeClosed(1, 10234).mapToObj(ContentExportSnapshotTest::call).toList();
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                10234L,
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
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(int index) {
    return call(
        index,
        List.of(
            Map.of(
                "role",
                "assistant",
                "type",
                "text",
                "text",
                "synthetic response "
                    + index
                    + " token=synthetic-secret /Users/alice/private-file <unsafe>")));
  }

  private static NormalizedCall call(int index, List<Map<String, Object>> sourceUnits) {
    return new NormalizedCall(
        "synthetic-" + index,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.of("same-turn"),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(1, 0, 0, 1, 2),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        sourceUnits,
        Map.of(),
        Map.of(),
        Optional.empty(),
        Optional.empty());
  }
}
