package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexRecordSpoolTest {
  @TempDir Path directory;

  @Test
  void allFieldsRoundTripIncludingUnknownPrecisionPresentEmptyAndUtf16() throws Exception {
    SourceRecord expected = record("prefix" + Character.toString(0xd800) + "后缀");
    try (var spool = new CodexRecordSpool()) {
      spool.add(expected);
      spool.add(expected);
      spool.seal();
      assertThat(Files.getPosixFilePermissions(spool.directory()))
          .isEqualTo(PosixFilePermissions.fromString("rwx------"));
      try (var first = spool.openCursor();
          var second = spool.openCursor(1)) {
        assertThat(first.next()).isEqualTo(expected);
        assertThat(second.next()).isEqualTo(expected);
        assertThat(first.next()).isEqualTo(expected);
        assertThat(first.hasNext()).isFalse();
        assertThatThrownBy(first::next).isInstanceOf(NoSuchElementException.class);
      }
      try (var end = spool.openCursor(2)) {
        assertThat(end.hasNext()).isFalse();
      }
      assertThatThrownBy(() -> spool.openCursor(-1)).isInstanceOf(IllegalArgumentException.class);
      assertThatThrownBy(() -> spool.openCursor(3)).isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void cursorCloseDoesNotCloseOwnerAndOwnerCloseInvalidatesEveryCursor() throws Exception {
    var spool = new CodexRecordSpool();
    Path temp = spool.directory();
    spool.add(record("visible"));
    spool.seal();
    var first = spool.openCursor();
    var second = spool.openCursor();
    first.close();
    assertThatThrownBy(first::hasNext).isInstanceOf(IOException.class);
    assertThat(second.next().content()).isEqualTo("visible");
    spool.close();
    spool.close();
    assertThat(spool.recordCount()).isEqualTo(1);
    assertThatThrownBy(second::hasNext).isInstanceOf(IOException.class);
    assertThatThrownBy(spool::openCursor).isInstanceOf(IOException.class);
    second.close();
    assertThat(temp).doesNotExist();
  }

  @Test
  void corruptIndexAndConstructorFailureAreIoErrorsAndCleanupStillRuns() throws Exception {
    Path temp;
    try (var spool = new CodexRecordSpool()) {
      temp = spool.directory();
      var value = record("visible");
      spool.add(value);
      spool.seal();
      try (var channel = FileChannel.open(temp.resolve("data"), StandardOpenOption.WRITE)) {
        channel.write(ByteBuffer.allocate(4).putInt(-1).flip(), 8L + value.locator().length() * 2L);
      }
      try (var cursor = spool.openCursor()) {
        assertThatThrownBy(cursor::next).isInstanceOf(IOException.class).hasMessageContaining("校验");
      }
      try (var channel = FileChannel.open(temp.resolve("index"), StandardOpenOption.WRITE)) {
        channel.write(ByteBuffer.allocate(8).putLong(-1).flip(), 0);
      }
      try (var cursor = spool.openCursor()) {
        assertThatThrownBy(cursor::next).isInstanceOf(IOException.class).hasMessageContaining("索引");
      }
    }
    assertThat(temp).doesNotExist();
  }

  @Test
  void legalBodyBitFlipIsNotSilentlyReturnedAsDifferentValidText() throws Exception {
    try (var spool = new CodexRecordSpool()) {
      String body = "CRC sentinel body 123";
      spool.add(record(body));
      spool.seal();
      Path data = spool.directory().resolve("data");
      byte[] encoded = Files.readAllBytes(data);
      byte[] needle = body.getBytes(java.nio.charset.StandardCharsets.UTF_16BE);
      int found = -1;
      for (int index = 0; index <= encoded.length - needle.length; index++) {
        if (java.util.Arrays.equals(
            encoded, index, index + needle.length, needle, 0, needle.length)) {
          found = index;
          break;
        }
      }
      assertThat(found).isNotNegative();
      encoded[found + 1] ^= 1;
      Files.write(data, encoded, StandardOpenOption.TRUNCATE_EXISTING);
      try (var cursor = spool.openCursor()) {
        assertThatThrownBy(cursor::next).isInstanceOf(IOException.class).hasMessageContaining("校验");
      }
    }
  }

  @Test
  void sealedDataOrIndexAppendIsExplicitIoFailure() throws Exception {
    for (String name : List.of("data", "index")) {
      try (var spool = new CodexRecordSpool()) {
        spool.add(record("visible"));
        spool.seal();
        Files.write(spool.directory().resolve(name), new byte[] {1}, StandardOpenOption.APPEND);
        assertThatThrownBy(
                () -> {
                  try (var cursor = spool.openCursor()) {
                    cursor.next();
                  }
                })
            .isInstanceOf(IOException.class)
            .hasMessageContaining("长度");
      }
    }
  }

  @Test
  void fingerprintHitRequiresFullEqualsAndNeverCrossesSegments() {
    var plan = new CodexFallbackPlan();
    plan.add(1, 7, "same body");
    assertThat(plan.contains(1, "same body", ordinal -> "different body")).isFalse();
    assertThat(plan.contains(1, "same body", ordinal -> ordinal == 7 ? "same body" : "wrong"))
        .isTrue();
    assertThat(plan.contains(2, "same body", ordinal -> "same body")).isFalse();
  }

  @Test
  void smallCompatibilityAndFewRecordsLargePayloadChooseDifferentRepresentations()
      throws Exception {
    var adapter = new CodexSourceAdapter();
    Path file = directory.resolve("source.jsonl");
    for (String body : List.of("small visible", "T".repeat(1_100_000))) {
      Files.writeString(
          file,
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":\""
              + body
              + "\"}}\n");
      var candidate =
          new Candidate(adapter.fingerprint(file), "synthetic-spool", "synthetic", Map.of());
      try (var success = (SourceResult.Success) adapter.parse(candidate, null)) {
        assertThat(success.hasManagedRecords()).isEqualTo(body.length() > 100);
        if (!success.hasManagedRecords()) {
          assertThat(success.records())
              .singleElement()
              .satisfies(r -> assertThat(r.content()).isEqualTo(body));
          assertThatThrownBy(() -> success.records().clear())
              .isInstanceOf(UnsupportedOperationException.class);
        } else assertThatThrownBy(success::records).isInstanceOf(IllegalStateException.class);
        try (var cursor = success.recordSequence().openCursor()) {
          assertThat(cursor.next().content()).isEqualTo(body);
        }
      }
    }
  }

  @Test
  void cancellationDoesNotPublishPartialSuccessOrLeakAnyMappedSpool() throws Exception {
    var adapter = new CodexSourceAdapter();
    Path file =
        Files.writeString(directory.resolve("cancel.jsonl"), "{\"type\":\"unknown\"}\n".repeat(4));
    var candidate =
        new Candidate(adapter.fingerprint(file), "synthetic-cancel", "synthetic", Map.of());
    var before = spoolDirectories();
    var checks = new AtomicInteger();
    assertThat(adapter.parse(candidate, () -> checks.incrementAndGet() >= 3))
        .isInstanceOf(SourceResult.Skipped.class);
    assertThat(spoolDirectories()).containsExactlyInAnyOrderElementsOf(before);
  }

  private static List<Path> spoolDirectories() throws IOException {
    try (var paths = Files.list(Path.of(System.getProperty("java.io.tmpdir")))) {
      return paths
          .filter(p -> p.getFileName().toString().startsWith("feipi-codex-records-"))
          .toList();
    }
  }

  private static SourceRecord record(String body) {
    return new SourceRecord(
        "synthetic#event[0]",
        0,
        "assistant",
        Optional.of("call"),
        Optional.of("synthetic-model"),
        Optional.of("2026-01-01T00:00:00Z"),
        Optional.of("turn"),
        new SourceRecordUsage(
            0,
            2,
            3,
            4,
            Map.of(
                "fresh_input_precision", "unavailable", "output_precision", "provider_reported")),
        List.of(new SourceToolCall("tool", "synthetic", "{\"argument\":\"value\"}")),
        Optional.of("tool"),
        Optional.of("synthetic"),
        Optional.of("synthetic error"),
        new SourceRecordRelation(
            Optional.of("child"),
            Optional.of("parent"),
            Optional.of("tool"),
            Optional.of("call"),
            Optional.of("synthetic")),
        body,
        Optional.of("message"),
        Optional.of("end_turn"),
        new SourceTiming(
            "task_complete",
            "turn",
            Optional.of(""),
            Optional.of("2026-01-01T00:00:00Z"),
            OptionalLong.of(0),
            OptionalLong.of(2),
            OptionalLong.empty(),
            "event"),
        true,
        Optional.of("assistant"));
  }
}
