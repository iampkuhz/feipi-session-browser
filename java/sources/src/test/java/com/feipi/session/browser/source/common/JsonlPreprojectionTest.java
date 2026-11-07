package com.feipi.session.browser.source.common;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.function.UnaryOperator;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JsonlPreprojectionTest {
  @TempDir Path directory;

  @Test
  void changedSourceRemainsRetryable() throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("changing.jsonl"), "{\"type\":\"known\",\"opaque\":\"large\"}\n");
    var reader =
        new JsonlReader(
            JsonlReaderConfig.DEFAULT,
            path -> {
              try {
                Files.writeString(path, "\n", java.nio.file.StandardOpenOption.APPEND);
              } catch (java.io.IOException failure) {
                throw new java.io.UncheckedIOException(failure);
              }
            });
    var result =
        reader.readPreprojected(
            file,
            List.of(new JsonlPreprojection.Rule("opaque", "known", "", Set.of())),
            UnaryOperator.identity());
    assertThat(result.diagnostics()).anyMatch(d -> d.code().equals("RETRYABLE_INCOMPLETE"));
    assertThat(result.events()).hasSize(1);
  }

  @Test
  void defaultUtf8AndTruncationFailuresAreNotHiddenInSkippedValue() throws Exception {
    Path file = directory.resolve("invalid.jsonl");
    Files.writeString(file, "{\"type\":\"known\",\"opaque\":\"");
    Files.write(file, new byte[] {(byte) 0xc3, 0x28}, java.nio.file.StandardOpenOption.APPEND);
    Files.writeString(file, "\"}\n", java.nio.file.StandardOpenOption.APPEND);
    var reader = new JsonlReader();
    var rules = List.of(new JsonlPreprojection.Rule("opaque", "known", "", Set.of()));
    var invalid = reader.readPreprojected(file, rules, UnaryOperator.identity());
    assertThat(invalid.events()).isEmpty();
    assertThat(invalid.diagnostics())
        .singleElement()
        .satisfies(d -> assertThat(d.code()).contains("INVALID_UTF8"));
    Files.writeString(file, "{\"type\":\"known\",\"opaque\":\"unfinished");
    var truncated = reader.readPreprojected(file, rules, UnaryOperator.identity());
    assertThat(truncated.events()).isEmpty();
    assertThat(truncated.diagnostics()).isEqualTo(reader.read(file).diagnostics());
  }

  @Test
  void lineLimitAndPhysicalWhitespaceStatsKeepExistingContract() throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("limit.jsonl"),
            "\ufeff{\"type\":\"known\",\"opaque\":[\r\n"
                + "\"gone\"\r\n"
                + "]}\r\n"
                + "\u2003\r"
                + "{\"second\":true}\n");
    var rules = List.of(new JsonlPreprojection.Rule("opaque", "known", "", Set.of()));
    var reader = new JsonlReader(new JsonlReaderConfig(1, 500, 40));
    var raw = reader.read(file);
    var projected = reader.readPreprojected(file, rules, UnaryOperator.identity());
    assertThat(projected.stats()).isEqualTo(raw.stats());
    assertThat(projected.stoppedByLimit()).isTrue();
    assertThat(projected.diagnostics()).isEqualTo(raw.diagnostics());
  }

  @Test
  void privateSpoolIsRemovedOnClose() throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("cleanup.jsonl"), "{\"type\":\"known\",\"opaque\":\"large\"}\n");
    Path temporary;
    try (var projection =
        JsonlPreprojection.create(
            file, List.of(new JsonlPreprojection.Rule("opaque", "known", "", Set.of())), 500)) {
      temporary = projection.projected();
      assertThat(temporary).exists();
      assertThat(Files.getPosixFilePermissions(temporary.getParent()))
          .isEqualTo(java.nio.file.attribute.PosixFilePermissions.fromString("rwx------"));
    }
    assertThat(temporary.getParent()).doesNotExist();
  }

  @Test
  void invalidUnicodeEscapeInsideOpaqueValueIsNeverHidden() throws Exception {
    String json = "{\"type\":\"known\",\"opaque\":\"" + Character.toString(92) + "uＦFFF\"}";
    Path file = Files.writeString(directory.resolve("escape.jsonl"), json);
    var reader = new JsonlReader();
    var result =
        reader.readPreprojected(
            file,
            List.of(new JsonlPreprojection.Rule("opaque", "known", "", Set.of())),
            UnaryOperator.identity());
    assertThat(result.events()).isEmpty();
    assertThat(result.diagnostics()).isEqualTo(reader.read(file).diagnostics());
  }
}
