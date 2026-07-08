package com.feipi.session.browser.contracttest.sourcejson;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderConfig;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** JsonlReader API 契约测试。 */
class JsonlReaderContractTest {

  @TempDir Path tempDir;

  @Test
  void emptyFileReturnsEmptyResult() throws IOException {
    Path file = tempDir.resolve("empty.jsonl");
    Files.writeString(file, "");
    JsonlReaderResult result = new JsonlReader().read(file);
    assertThat(result.events()).isEmpty();
    assertThat(result.diagnostics()).isEmpty();
  }

  @Test
  void resultIsImmutable() throws IOException {
    Path file = tempDir.resolve("test.jsonl");
    Files.writeString(file, "{\"a\":1}\n");
    JsonlReaderResult result = new JsonlReader().read(file);
    assertThatThrownBy(() -> result.events().add(null))
        .isInstanceOf(UnsupportedOperationException.class);
  }

  @Test
  void configRejectsInvalidValues() {
    assertThatThrownBy(() -> new JsonlReaderConfig(0, 100, 100))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new JsonlReaderConfig(100, -1, 100))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
