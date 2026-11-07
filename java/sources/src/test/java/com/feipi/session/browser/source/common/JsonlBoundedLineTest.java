package com.feipi.session.browser.source.common;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.File;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.OptionalInt;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class JsonlBoundedLineTest {
  @TempDir Path directory;

  @Test
  void physicalLineLargerThanHeapRetainsOverflowAndNextRecord() throws Exception {
    Path file = directory.resolve("large.jsonl");
    try (var writer = Files.newBufferedWriter(file)) {
      writer.write("{\"large\":\"");
      String chunk = "x".repeat(65_536);
      for (int i = 0; i < 4096; i++) writer.write(chunk);
      writer.write("\"}\n{\"next\":true}");
    }
    var classpath = new LinkedHashSet<String>();
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof URLClassLoader urls) {
        for (var url : urls.getURLs())
          if ("file".equals(url.getProtocol())) classpath.add(Path.of(url.toURI()).toString());
      }
    }
    classpath.addAll(
        Arrays.asList(System.getProperty("java.class.path").split(File.pathSeparator)));
    Path log = directory.resolve("bounded-heap.log");
    var process =
        new ProcessBuilder(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx64m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName(),
                file.toString())
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .start();
    boolean completed = process.waitFor(90, TimeUnit.SECONDS);
    if (!completed) process.destroyForcibly();
    assertThat(completed).isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
  }

  @Test
  void trailingWhitespaceAndMixedTerminatorsKeepExactOffsets() throws Exception {
    Path file = directory.resolve("whitespace.jsonl");
    String first = "\uFEFF{}" + " \t".repeat(50_000) + "\r\n";
    String overflow = "{\"wide\":\"" + "界".repeat(100) + "\"}\r";
    Files.writeString(file, first + overflow + "{\"next\":true}", StandardCharsets.UTF_8);
    var result = new JsonlReader(JsonlReaderConfig.of(100, 32, 16)).read(file);
    assertThat(result.events()).hasSize(2);
    assertThat(result.events().getLast().path("next").asBoolean()).isTrue();
    assertThat(result.stats().totalLines()).isEqualTo(3);
    assertThat(result.diagnostics()).hasSize(1);
    var diagnostic = result.diagnostics().getFirst();
    assertThat(diagnostic.code()).isEqualTo("BAD_JSON:BUFFER_OVERFLOW");
    assertThat(diagnostic.byteRangeStart()).hasValue(first.getBytes(StandardCharsets.UTF_8).length);
    assertThat(diagnostic.byteRangeEnd())
        .hasValue((first + overflow).getBytes(StandardCharsets.UTF_8).length);
  }

  @Test
  void overflowDrainStillRejectsInvalidUtf8AndClearsPriorEvents() throws Exception {
    Path file = directory.resolve("invalid.jsonl");
    byte[] prefix = ("{}\n{\"value\":\"" + "x".repeat(1000)).getBytes(StandardCharsets.UTF_8);
    byte[] bytes = Arrays.copyOf(prefix, prefix.length + 3);
    bytes[prefix.length] = (byte) 0xc3;
    bytes[prefix.length + 1] = 0x28;
    bytes[prefix.length + 2] = '\n';
    Files.write(file, bytes);
    var result = new JsonlReader(JsonlReaderConfig.of(100, 32, 16)).read(file);
    assertThat(result.events()).isEmpty();
    assertThat(result.diagnostics()).hasSize(1);
    assertThat(result.diagnostics().getFirst().code()).isEqualTo("BAD_JSON:INVALID_UTF8");
    assertThat(result.diagnostics().getFirst().preview()).isEmpty();
  }

  @Test
  void multilineBudgetAndNonBmpCharactersUseUtf16Units() throws Exception {
    Path file = directory.resolve("multiline.jsonl");
    Files.writeString(file, "{\n\"wide\":\"" + "😀".repeat(10) + "\"}\n{\"next\":true}\n");
    var result = new JsonlReader(JsonlReaderConfig.of(100, 25, 16)).read(file);
    assertThat(result.diagnostics()).anyMatch(d -> d.code().equals("BAD_JSON:BUFFER_OVERFLOW"));
    assertThat(result.events()).hasSize(1);
    assertThat(result.events().getFirst().path("next").asBoolean()).isTrue();
  }

  @Test
  void byteRangeOutsideOldApiIsUnknownRatherThanWrapped() throws Exception {
    var method = JsonlReader.class.getDeclaredMethod("optionalByte", long.class);
    method.setAccessible(true);
    assertThat((OptionalInt) method.invoke(null, (long) Integer.MAX_VALUE))
        .hasValue(Integer.MAX_VALUE);
    assertThat((OptionalInt) method.invoke(null, (long) Integer.MAX_VALUE + 1)).isEmpty();
    assertThat((OptionalInt) method.invoke(null, -1L)).isEmpty();
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      var result = new JsonlReader().read(Path.of(args[0]));
      if (result.events().size() != 1
          || !result.events().getFirst().path("next").asBoolean()
          || result.stats().totalLines() != 2
          || result.diagnostics().size() != 1
          || !result.diagnostics().getFirst().code().equals("BAD_JSON:BUFFER_OVERFLOW")
          || result.diagnostics().getFirst().byteRangeEnd().orElseThrow() != 268_435_469)
        throw new AssertionError("overflow/next record/physical positions changed");
    }
  }
}
