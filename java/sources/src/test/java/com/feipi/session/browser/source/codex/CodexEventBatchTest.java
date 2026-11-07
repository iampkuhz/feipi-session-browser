package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderConfig;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexEventBatchTest {
  @TempDir Path directory;

  @Test
  void replayPreservesProjectionUnknownFieldsDiagnosticsAndRawPositions() throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("events.jsonl"),
            "\ufeff{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool\",\"output\":[{\"type\":\"input_text\",\"text\":\"工具正文\"},{\"type\":\"input_image\",\"image_url\":\"data:image/png;base64,AAAA\"}],\"unknown\":{\"keep\":true}}}\r\n"
                + "{bad}\r"
                + "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"response\",\"usage\":{\"input_tokens\":7,\"cached_input_tokens\":0,\"cache_creation_input_tokens\":0,\"output_tokens\":3}}}{\"last\":true}");
    var reader = new JsonlReader();
    var expected = CodexEventProjection.read(reader, file);
    try (var batch = CodexEventBatch.read(reader, file)) {
      assertThat(batch.events()).containsExactlyElementsOf(expected.events());
      assertThat(batch.result().events()).isEmpty();
      assertThat(batch.result().diagnostics()).isEqualTo(expected.diagnostics());
      assertThat(batch.result().stats()).isEqualTo(expected.stats());
      ((com.fasterxml.jackson.databind.node.ObjectNode) batch.events().getFirst().path("payload"))
          .remove("output");
      assertThat(batch.events().getFirst()).isEqualTo(expected.events().getFirst());
    }
  }

  @Test
  void invalidUtf8RollsBackAlreadyEmittedRecordsAndLimitKeepsOldSemantics() throws Exception {
    Path file = Files.writeString(directory.resolve("invalid.jsonl"), "{\"valid\":true}\n");
    Files.write(file, new byte[] {(byte) 0xc3, 0x28}, StandardOpenOption.APPEND);
    try (var batch = CodexEventBatch.read(new JsonlReader(), file)) {
      assertThat(batch.events()).isEmpty();
      assertThat(batch.result().stats().eventsParsed()).isZero();
      assertThat(batch.result().diagnostics())
          .singleElement()
          .satisfies(d -> assertThat(d.code()).contains("INVALID_UTF8"));
    }
    Files.writeString(file, "{\"first\":true}\r\n{\"second\":true}\n");
    var reader = new JsonlReader(new JsonlReaderConfig(1, 500, 40));
    var expected = CodexEventProjection.read(reader, file);
    try (var batch = CodexEventBatch.read(reader, file)) {
      assertThat(batch.events()).containsExactlyElementsOf(expected.events());
      assertThat(batch.result().stats()).isEqualTo(expected.stats());
      assertThat(batch.result().stoppedByLimit()).isEqualTo(expected.stoppedByLimit());
      assertThat(batch.result().diagnostics()).isEqualTo(expected.diagnostics());
    }
  }

  @Test
  void spoolIsOwnerOnlyAndFailureAndNormalCloseDeleteAllResources() throws Exception {
    Path temporary;
    var spool = new CodexEventSpool();
    try (spool) {
      temporary = spool.directory();
      assertThat(Files.getPosixFilePermissions(temporary))
          .isEqualTo(PosixFilePermissions.fromString("rwx------"));
      spool.add(new ObjectMapper().readTree("{\"text\":\"complete\"}"));
      spool.seal();
      Files.writeString(temporary.resolve("events"), "", StandardOpenOption.TRUNCATE_EXISTING);
      assertThatThrownBy(() -> spool.getFirst()).isInstanceOf(UncheckedIOException.class);
    }
    assertThat(temporary).doesNotExist();
    spool.close();
    assertThatThrownBy(() -> spool.getFirst()).isInstanceOf(IllegalStateException.class);
  }
}
