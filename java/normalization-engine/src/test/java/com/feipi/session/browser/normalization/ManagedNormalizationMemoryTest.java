package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import java.io.File;
import java.io.IOException;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.AbstractList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** C7.3：相同 96×900000 正文输入通过 managed API 在原 64MiB child 重放。 */
class ManagedNormalizationMemoryTest {
  @TempDir Path directory;
  private static final int COUNT = 96;
  private static final int LENGTH = 900_000;

  @Test
  void normalizationReplaysAboveHeapWithoutMaterializingAllRecordBodies() throws Exception {
    runChild();
  }

  @Test
  void legacySmallInputKeepsGlobalIdentityUsageAndBody() throws Exception {
    verify(3, 128, false);
  }

  @Test
  void legacyInterleavedScopesKeepRepeatedBodiesToolsAndLateResponseOrder() {
    var input =
        List.of(
            smallRecord("main", 0, "user", "same body"),
            smallRecord("child", 1, "user", "child question"),
            smallRecord("main", 2, "assistant", "same body"),
            smallRecord("child", 3, "assistant", "child answer"),
            smallRecord("main", 4, "response_item", "late response"),
            smallTool("main", 5),
            smallRecord("child", 6, "neutral", "not a visible response"),
            smallRecord("main", 7, "user", "next question"),
            smallRecord("main", 8, "assistant", "final answer"));
    var expected =
        List.of(
            List.of(
                Map.of("type", "user", "role", "user", "text", "same body"),
                Map.of("type", "assistant", "role", "assistant", "text", "same body"),
                Map.of(
                    "type",
                    "tool_use",
                    "role",
                    "assistant",
                    "text",
                    "",
                    "id",
                    "tool-5",
                    "name",
                    "synthetic-tool",
                    "input",
                    "{}"),
                Map.of("type", "response_item", "role", "assistant", "text", "late response")),
            List.of(
                Map.of("type", "user", "role", "user", "text", "child question"),
                Map.of("type", "assistant", "role", "assistant", "text", "child answer")),
            List.of(
                Map.of("type", "user", "role", "user", "text", "next question"),
                Map.of("type", "assistant", "role", "assistant", "text", "final answer")));
    // 完整比较小输入的 canonical 内容，避免重复正文被去重或 EOF 回填丢失。
    for (int pass = 0; pass < 2; pass++) {
      assertThat(CallSourceUnitBuilder.build(input, SourceRecord::locator)).isEqualTo(expected);
    }
  }

  private static SourceRecord smallRecord(String scope, int index, String type, String text) {
    return new SourceRecord(
        scope,
        index,
        type,
        Optional.of("small-call-" + index),
        Optional.of("synthetic-model"),
        Optional.empty(),
        Optional.of("turn-" + index % 2),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        text);
  }

  private static SourceRecord smallTool(String scope, int index) {
    return new SourceRecord(
        scope,
        index,
        "tool_use",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(
            new com.feipi.session.browser.domain.source.SourceToolCall(
                "tool-" + index, "synthetic-tool", "{}")),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        "");
  }

  private static List<SourceRecord> records(int count, int length) {
    // 不在父进程或输入容器缓存正文；旧入口的 copy/classify/build 自行暴露驻留。
    return new AbstractList<>() {
      @Override
      public int size() {
        return count;
      }

      @Override
      public SourceRecord get(int index) {
        java.util.Objects.checkIndex(index, count);
        return new SourceRecord(
                "synthetic/events#event[" + index + "]",
                index,
                "assistant",
                Optional.of("call-" + index),
                Optional.of("synthetic-model"),
                Optional.empty(),
                Optional.of("shared-turn"),
                new SourceRecordUsage(3, 2, 1, 4),
                List.of(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                SourceRecordRelation.empty(),
                body(index, length))
            .withMessageRole(Optional.of("assistant"));
      }
    };
  }

  private static void verify(int count, int length, boolean managed) throws Exception {
    // 各heap pool的peak之和不是同一时刻RSS；只报告，不用波动数值作为通过阈值。
    for (var pool : java.lang.management.ManagementFactory.getMemoryPoolMXBeans()) {
      if (pool.getType() == java.lang.management.MemoryType.HEAP) pool.resetPeakUsage();
    }
    System.out.println(
        "stage=normalizeContent-global-plan-replay count=" + count + " length=" + length);
    var engine = new NormalizationEngine();
    try (var sequence = generatedSequence(count, length)) {
      var content =
          managed
              ? engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
              : engine.normalizeContent(
                  NormalizedAgent.CODEX, records(count, length), List.of(), List.of());
      if (managed) {
        verifyPlanHasNoBodies(content);
        System.gc();
        System.out.println(
            "plan-retained count="
                + count
                + " length="
                + length
                + " heapUsed="
                + java.lang.management.ManagementFactory.getMemoryMXBean()
                    .getHeapMemoryUsage()
                    .getUsed());
      }
      if (content.header().agent() != NormalizedAgent.CODEX
          || content.header().totals().get("calls") != count)
        throw new AssertionError("header calls");
      for (int pass = 0; pass < 2; pass++) {
        int seen = 0;
        try (var cursor = content.openCursor()) {
          while (cursor.hasNext()) {
            var unit = cursor.next();
            for (var call : unit.calls()) {
              int index = seen++;
              if (call.callIndex() != index + 1
                  || !call.callId().equals("call-" + index)
                  || !call.turnId().equals(Optional.of("shared-turn")))
                throw new AssertionError("global identity");
              if (call.usage().fresh() != 3
                  || call.usage().cacheRead() != 2
                  || call.usage().cacheWrite() != 1
                  || call.usage().output() != 4
                  || call.usage().total() != 10) throw new AssertionError("tokens");
              var bodies =
                  call.sourceUnits().stream()
                      .filter(value -> "assistant".equals(value.get("type")))
                      .toList();
              if (bodies.size() != 1) throw new AssertionError("response occurrence");
              var body = bodies.getFirst();
              if (!"assistant".equals(body.get("role"))
                  || !Arrays.equals(hash(body(index, length)), hash((String) body.get("text"))))
                throw new AssertionError("role/text SHA");
            }
          }
        }
        if (seen != count) throw new AssertionError("tail/count");
      }
      long peakSum =
          java.lang.management.ManagementFactory.getMemoryPoolMXBeans().stream()
              .filter(pool -> pool.getType() == java.lang.management.MemoryType.HEAP)
              .mapToLong(pool -> pool.getPeakUsage().getUsed())
              .sum();
      if (managed)
        System.out.println(
            "growth-evidence count="
                + count
                + " length="
                + length
                + " heapPoolPeakSum="
                + peakSum
                + " planContainsSourceRecord=false planContainsFixtureBody=false");
      System.out.println("stage=verified passes=2 count=" + count);
    }
  }

  private static void verifyPlanHasNoBodies(Object content) throws Exception {
    var field = content.getClass().getDeclaredField("plan");
    field.setAccessible(true);
    Object plan = field.get(content);
    var seen =
        java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<Object, Boolean>());
    inspectPlan(plan, seen);
    var facts = plan.getClass().getDeclaredField("facts");
    var frames = plan.getClass().getDeclaredField("frames");
    facts.setAccessible(true);
    frames.setAccessible(true);
    System.out.println(
        "plan-structure facts="
            + ((List<?>) facts.get(plan)).size()
            + " frames="
            + ((List<?>) frames.get(plan)).size()
            + " visitedObjects="
            + seen.size());
  }

  private static void inspectPlan(Object value, java.util.Set<Object> seen) throws Exception {
    if (value == null || !seen.add(value)) return;
    if (value instanceof SourceRecord) throw new AssertionError("plan retains SourceRecord");
    // 所有 fixture 身份与元数据都短于256；正文长串一旦进入计划即确定失败。
    if (value instanceof String text) {
      if (text.length() > 256 || text.startsWith("synthetic-answer-"))
        throw new AssertionError("plan retains fixture body");
      return;
    }
    if (value instanceof Map<?, ?> map) {
      for (var entry : map.entrySet()) {
        inspectPlan(entry.getKey(), seen);
        inspectPlan(entry.getValue(), seen);
      }
    } else if (value instanceof Iterable<?> iterable) {
      for (Object item : iterable) inspectPlan(item, seen);
    } else if (value instanceof Optional<?> optional) {
      if (optional.isPresent()) inspectPlan(optional.get(), seen);
    } else if (value.getClass().getPackageName().startsWith("com.feipi.session.browser.")) {
      for (var field : value.getClass().getDeclaredFields()) {
        if (java.lang.reflect.Modifier.isStatic(field.getModifiers())) continue;
        field.setAccessible(true);
        inspectPlan(field.get(value), seen);
      }
    }
  }

  private static SourceRecordSequence generatedSequence(int count, int length) {
    return new SourceRecordSequence() {
      private boolean closed;

      @Override
      public long recordCount() {
        return count;
      }

      @Override
      public RecordCursor openCursor(long ordinal) throws IOException {
        if (closed) throw new IOException("closed sequence");
        if (ordinal < 0 || ordinal > count) throw new IllegalArgumentException("ordinal");
        return new RecordCursor() {
          private int index = (int) ordinal;
          private boolean cursorClosed;

          @Override
          public boolean hasNext() throws IOException {
            if (closed || cursorClosed) throw new IOException("closed cursor");
            return index < count;
          }

          @Override
          public SourceRecord next() throws IOException {
            if (!hasNext()) throw new java.util.NoSuchElementException();
            return records(count, length).get(index++);
          }

          @Override
          public void close() {
            cursorClosed = true;
          }
        };
      }

      @Override
      public void close() {
        closed = true;
      }
    };
  }

  public static final class HeapProbe {
    public static void main(String[] args) throws Exception {
      verify(COUNT, 128, true);
      verify(COUNT, LENGTH, true);
      verify(1024, 1024, true);
    }
  }

  private static String body(int index, int length) {
    String prefix = "synthetic-answer-" + index + ":";
    return prefix + "T".repeat(length - prefix.length());
  }

  private static byte[] hash(String text) throws Exception {
    return MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
  }

  private void runChild(String... arguments) throws Exception {
    var classpath = new LinkedHashSet<String>();
    for (ClassLoader loader = getClass().getClassLoader();
        loader != null;
        loader = loader.getParent()) {
      if (loader instanceof URLClassLoader urls) {
        for (var url : urls.getURLs()) classpath.add(Path.of(url.toURI()).toString());
      }
    }
    classpath.addAll(
        Arrays.asList(System.getProperty("java.class.path").split(File.pathSeparator)));
    var command =
        new java.util.ArrayList<>(
            List.of(
                Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-XX:+UseSerialGC",
                "-Xms16m",
                "-Xmx64m",
                "-cp",
                String.join(File.pathSeparator, classpath),
                HeapProbe.class.getName()));
    command.addAll(List.of(arguments));
    Path log = directory.resolve("child.log");
    var process =
        new ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log.toFile()).start();
    boolean finished = process.waitFor(180, TimeUnit.SECONDS);
    if (!finished) {
      process.destroyForcibly();
      process.waitFor(10, TimeUnit.SECONDS);
    }
    assertThat(finished).as("child timeout").isTrue();
    assertThat(process.exitValue()).as(Files.readString(log)).isZero();
    String childOutput = Files.readString(log);
    System.out.print(childOutput);
    assertThat(childOutput)
        .contains(
            "stage=verified passes=2 count=96",
            "growth-evidence count=96 length=128",
            "growth-evidence count=96 length=900000",
            "growth-evidence count=1024 length=1024",
            "planContainsSourceRecord=false planContainsFixtureBody=false");
  }
}
