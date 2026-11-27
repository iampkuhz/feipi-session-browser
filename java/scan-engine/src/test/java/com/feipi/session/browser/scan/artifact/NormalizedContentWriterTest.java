package com.feipi.session.browser.scan.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class NormalizedContentWriterTest {
  @TempDir Path directory;

  @Test
  void missingOwnerMarkerIsNotAStrongCallReferenceButOtherDanglingCallsRemainRejected()
      throws Exception {
    var writer = new NormalizedArtifactWriter();
    var unknown = ownerContent("unknown", java.util.Optional.empty());
    var written = writer.writeContent(directory, unknown, Map.of());
    assertThat(writer.validate(written.dataPath(), written.metaPath())).isTrue();
    for (var content :
        List.of(
            ownerContent("missing-call", java.util.Optional.empty()),
            ownerContent("unknown", java.util.Optional.of("unknown")),
            ownerContent("unknown", java.util.Optional.of("missing-consumer")))) {
      assertThatThrownBy(() -> writer.writeContent(directory, content, Map.of()))
          .isInstanceOf(IOException.class)
          .hasMessageContaining("unresolved strong content reference");
    }
  }

  private static NormalizedSessionContent ownerContent(
      String owner, java.util.Optional<String> consumer) {
    var tool =
        new com.feipi.session.browser.domain.normalized.NormalizedToolExecution(
            "synthetic-orphan",
            "exec_command",
            com.feipi.session.browser.domain.enums.CallScope.MAIN,
            owner,
            consumer,
            java.util.Optional.empty(),
            java.util.Optional.empty(),
            null,
            List.of(),
            java.util.Optional.empty(),
            java.util.Optional.empty());
    return NormalizedSessionContent.fromArtifact(
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of("session_key", "synthetic-owner-marker"),
            List.of(),
            List.of(tool),
            List.of(),
            Map.of(),
            Map.of()));
  }

  @Test
  void writesDeterministicTaggedContentWithExactHashAndSize() throws Exception {
    var content = minimal();
    var writer = new NormalizedArtifactWriter();
    var result = writer.writeContent(directory, content, Map.of());
    String first = Files.readString(result.dataPath());
    assertThat(first)
        .contains("\"storageFormat\":\"session-content.units.v1\"")
        .contains("\"unitIndex\":0")
        .contains("\"schemaVersion\"");
    assertThat(result.contentSize()).isEqualTo(Files.size(result.dataPath()));
    assertThat(writer.validate(result.dataPath(), result.metaPath())).isTrue();
    var second = writer.writeContent(directory, content, Map.of());
    assertThat(second.contentHash()).isEqualTo(result.contentHash());
  }

  @Test
  void interruptedCursorClosesWithoutPublishingOrOverwritingPriorContent() throws Exception {
    var writer = new NormalizedArtifactWriter();
    var prior = writer.writeContent(directory, minimal(), Map.of());
    String before = Files.readString(prior.dataPath());
    boolean[] closed = {false};
    var broken =
        new NormalizedSessionContent() {
          public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
            return minimal().header();
          }

          public ContentCursor openCursor() {
            return new ContentCursor() {
              public boolean hasNext() throws IOException {
                throw new IOException("synthetic interruption");
              }

              public com.feipi.session.browser.domain.normalized.NormalizedContentUnit next() {
                throw new java.util.NoSuchElementException();
              }

              public void close() {
                closed[0] = true;
              }
            };
          }
        };
    assertThatThrownBy(() -> writer.writeContent(directory, broken, Map.of()))
        .isInstanceOf(IOException.class)
        .hasMessageContaining("synthetic interruption");
    assertThat(closed[0]).isTrue();
    assertThat(Files.readString(prior.dataPath())).isEqualTo(before);
    assertThat(writer.validate(prior.dataPath(), prior.metaPath())).isTrue();
  }

  @Test
  void largeContentWritesEveryIndependentCallAndTextInGlobalOrder() throws Exception {
    int size = 10_234;
    var records =
        java.util.stream.IntStream.range(0, size)
            .mapToObj(
                i ->
                    com.feipi.session.browser.domain.source.SourceRecord.of(
                            "synthetic/events#event[" + i + "]", i, "assistant")
                        .withContent("answer-" + i)
                        .withMessageRole(java.util.Optional.of("assistant")))
            .toList();
    var producer =
        new com.feipi.session.browser.normalization.NormalizationEngine()
            .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
    var session = new java.util.LinkedHashMap<String, Object>(producer.header().session().toMap());
    session.put("session_key", "synthetic-large-writer");
    var content =
        producer.withHeader(
            new com.feipi.session.browser.domain.normalized.NormalizedContentHeader(
                producer.header().schemaVersion(),
                producer.header().agent(),
                com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata.fromMap(
                    session),
                producer.header().totals()));
    var writer = new NormalizedArtifactWriter();
    var written = writer.writeContent(directory, content, Map.of());
    long calls = 0;
    long units = 0;
    var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
    try (var parser = mapper.getFactory().createParser(written.dataPath().toFile())) {
      while (parser.nextToken() != null) {
        if (parser.currentToken() == com.fasterxml.jackson.core.JsonToken.FIELD_NAME
            && "unitIndex".equals(parser.currentName())) {
          parser.nextToken();
          assertThat(parser.getLongValue()).isEqualTo(units++);
        }
        if (parser.currentToken() == com.fasterxml.jackson.core.JsonToken.FIELD_NAME
            && "calls".equals(parser.currentName())) {
          parser.nextToken();
          if (parser.currentToken() == com.fasterxml.jackson.core.JsonToken.START_ARRAY) {
            while (parser.nextToken() != com.fasterxml.jackson.core.JsonToken.END_ARRAY) {
              com.fasterxml.jackson.databind.JsonNode call = mapper.readTree(parser);
              assertThat(call.path("call_index").longValue()).isEqualTo(++calls);
              assertThat(call.path("source_units").toString()).contains("answer-" + (calls - 1));
            }
          }
        }
      }
    }
    assertThat(calls).isEqualTo(size);
    assertThat(units).isEqualTo(size);
    assertThat(writer.validate(written.dataPath(), written.metaPath())).isTrue();
  }

  @Test
  void malformedTotalsAndDuplicateCallsNeverPublishMetadata() throws Exception {
    var producer =
        new com.feipi.session.browser.normalization.NormalizationEngine()
            .normalizeContent(
                NormalizedAgent.CODEX,
                List.of(
                    com.feipi.session.browser.domain.source.SourceRecord.of(
                        "synthetic#event[0]", 0, "assistant")),
                List.of(),
                List.of());
    var one = producer.toArtifact().calls().getFirst();
    var counts = new java.util.HashMap<>(minimal().header().totals());
    counts.put("calls", 2L);
    var header =
        new com.feipi.session.browser.domain.normalized.NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            minimal().header().session(),
            counts);
    var duplicates =
        NormalizedSessionContent.fromLists(
            header, List.of(), List.of(one, one), List.of(), List.of(), Map.of(), Map.of());
    assertThatThrownBy(
            () -> new NormalizedArtifactWriter().writeContent(directory, duplicates, Map.of()))
        .isInstanceOf(IOException.class)
        .hasMessageContaining("duplicate global callId");
    try (var paths = Files.list(directory)) {
      assertThat(paths.toList()).isEmpty();
    }
    counts.put("calls", 1L);
    var wrongTotals =
        minimal()
            .withHeader(
                new com.feipi.session.browser.domain.normalized.NormalizedContentHeader(
                    NormalizedConstants.SCHEMA_VERSION,
                    NormalizedAgent.CODEX,
                    minimal().header().session(),
                    counts));
    assertThatThrownBy(
            () -> new NormalizedArtifactWriter().writeContent(directory, wrongTotals, Map.of()))
        .isInstanceOf(IOException.class)
        .hasMessageContaining("totals mismatch");
  }

  private static NormalizedSessionContent minimal() {
    return NormalizedSessionContent.fromArtifact(
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of("session_key", "synthetic-content"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of()));
  }
}
