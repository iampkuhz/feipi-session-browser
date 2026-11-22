package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceReadingEvidence;
import com.feipi.session.browser.source.spi.SourceAdapter.CancellationSignal;
import java.io.BufferedReader;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** 按来源明确的分叉截止点重放父级历史。仅传出类别估算，绝不复制父级正文。 */
final class CodexForkReadingEvidence {
  private static final long MAX_BYTES = 64L * 1024 * 1024;
  private static final int MAX_LINE = 8 * 1024 * 1024;
  private static final int MAX_ORDINAL = 100_000;
  private static final Pattern THREAD =
      Pattern.compile("[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}");
  private static final String PUNCT = "{}()[]\"'\\;:,.<>+=~`/@#$%^&*|";
  private static final ObjectMapper JSON = new ObjectMapper();

  private CodexForkReadingEvidence() {}

  static List<SourceReadingEvidence> read(
      Path child, JsonNode metaEvent, CancellationSignal cancellation) {
    var meta = metaEvent.path("payload");
    var history = meta.path("history_base");
    var id = history.path("thread_id").asText();
    var limit = history.path("end_ordinal_exclusive");
    var bytes = history.path("end_byte_offset");
    if (!meta.path("attached_thread").isBoolean()
        || !meta.path("attached_thread").booleanValue()
        || !"paginated".equals(meta.path("history_mode").asText())
        || !THREAD.matcher(id).matches()
        || !id.equals(meta.path("forked_from_id").asText())
        || id.equals(meta.path("id").asText())
        || !positiveBound(limit, MAX_ORDINAL)
        || !limit.equals(meta.path("forked_from_ordinal_exclusive"))
        || !limit.equals(metaEvent.path("ordinal"))
        || !positiveBound(bytes, MAX_BYTES)) return List.of();
    try {
      Path parent = findParent(child, id);
      return parent == null
          ? List.of()
          : replay(
              parent,
              new Cut(
                  id,
                  limit.asInt(),
                  bytes.asLong(),
                  meta.path("base_instructions").path("text").asText("")),
              cancellation);
    } catch (IOException | SecurityException invalid) {
      // 文件缺失或边界不完整时不加归因；不影响侧聊自身索引。
      return List.of();
    }
  }

  private static boolean positiveBound(JsonNode value, long maximum) {
    return value.isIntegralNumber()
        && value.canConvertToLong()
        && value.asLong() > 0
        && value.asLong() <= maximum;
  }

  private static Path findParent(Path child, String id) throws IOException {
    Path file = child.toAbsolutePath().normalize();
    if (!file.equals(file.toRealPath(LinkOption.NOFOLLOW_LINKS))) return null;
    for (Path part = file; part != null; part = part.getParent()) {
      if (Files.isSymbolicLink(part)) return null;
    }
    Path rollouts = file.getParent();
    while (rollouts != null
        && !List.of("sessions", "archived_sessions")
            .contains(rollouts.getFileName() == null ? "" : rollouts.getFileName().toString())) {
      rollouts = rollouts.getParent();
    }
    if (rollouts == null) return null;
    var found = new ArrayList<Path>();
    for (String directory : List.of("sessions", "archived_sessions")) {
      Path root = rollouts.getParent().resolve(directory);
      if (!Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) continue;
      try (var files =
          Files.find(
              root,
              5,
              (path, attrs) ->
                  attrs.isRegularFile()
                      && path.getFileName().toString().startsWith("rollout-")
                      && path.getFileName().toString().endsWith("-" + id + ".jsonl"))) {
        found.addAll(files.limit(2).toList());
      }
    }
    return found.size() == 1 ? found.getFirst() : null;
  }

  private static List<SourceReadingEvidence> replay(
      Path parent, Cut cut, CancellationSignal cancellation) throws IOException {
    try (var channel =
        FileChannel.open(parent, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
      var last = ByteBuffer.allocate(1);
      if (channel.read(last, cut.bytes() - 1) != 1 || last.get(0) != '\n') return List.of();
      try (var in =
          new BufferedReader(
              new InputStreamReader(
                  new BoundedInput(Channels.newInputStream(channel), cut.bytes()),
                  StandardCharsets.UTF_8.newDecoder()))) {
        var parts = new EnumMap<Kind, Counter>(Kind.class);
        for (int ordinal = 0; ordinal < cut.ordinal(); ordinal++) {
          if (cancellation != null && cancellation.isCancelled()) return List.of();
          String line = in.readLine();
          if (line == null || line.length() > MAX_LINE) return List.of();
          var event = JSON.readTree(line);
          if (event == null) return List.of();
          var n = event.path("ordinal");
          if (!n.isIntegralNumber() || !n.canConvertToInt() || n.asInt() != ordinal)
            return List.of();
          String type = event.path("type").asText();
          var payload = event.path("payload");
          if (ordinal == 0
              && (!"session_meta".equals(type)
                  || !cut.thread().equals(payload.path("id").asText()))) return List.of();
          if ("compacted".equals(type)) {
            var snapshot = payload.path("replacement_history");
            if (!snapshot.isArray()) return List.of();
            parts.clear();
            snapshot.forEach(item -> project(parts, item, cut.sharedBase()));
          } else if ("response_item".equals(type)) {
            project(parts, payload, cut.sharedBase());
          } else if ("event_msg".equals(type)
              && "thread_rolled_back".equals(payload.path("type").asText())) {
            return List.of();
          }
        }
        return in.readLine() == null ? evidence(parts) : List.of();
      }
    }
  }

  private static void project(Map<Kind, Counter> parts, JsonNode item, String sharedBase) {
    switch (item.path("type").asText()) {
      case "message" -> {
        Kind kind =
            switch (item.path("role").asText()) {
              case "developer", "system" -> Kind.INSTRUCTIONS;
              case "user" -> Kind.USER;
              case "assistant" -> Kind.ASSISTANT;
              default -> null;
            };
        if (kind != null) text(parts, kind, item.path("content"), sharedBase);
      }
      case "function_call" -> add(parts, Kind.TOOL_INPUT, item.path("arguments").asText(""));
      case "custom_tool_call" -> add(parts, Kind.TOOL_INPUT, item.path("input").asText(""));
      case "function_call_output", "custom_tool_call_output" ->
          text(parts, Kind.TOOL_RESULT, item.path("output"), "");
      case "additional_tools" -> {
        var tools = item.path("tools");
        if (tools.isArray() && !tools.isEmpty())
          add(parts, Kind.TOOL_DEFINITIONS, tools.toString());
      }
      default -> {}
    }
  }

  private static void text(Map<Kind, Counter> parts, Kind kind, JsonNode data, String sharedBase) {
    if (data.isTextual() && !data.textValue().equals(sharedBase))
      add(parts, kind, data.textValue());
    if (!data.isArray()) return;
    for (var fragment : data) {
      if (List.of("input_text", "output_text", "text").contains(fragment.path("type").asText())) {
        String value = fragment.path("text").asText("");
        if (kind != Kind.INSTRUCTIONS || !value.equals(sharedBase)) add(parts, kind, value);
      }
    }
  }

  private static void add(Map<Kind, Counter> parts, Kind kind, String text) {
    if (text.isBlank()) return;
    parts.computeIfAbsent(kind, unused -> new Counter()).append(text);
  }

  private static List<SourceReadingEvidence> evidence(Map<Kind, Counter> parts) {
    return parts.entrySet().stream()
        .map(entry -> new SourceReadingEvidence(entry.getKey().key, entry.getValue().encoded()))
        .toList();
  }

  /**
   * 校验后的父级截止点。
   *
   * @param thread 父会话身份
   * @param ordinal 不包含的事件序号
   * @param bytes 不包含的文件字节位置
   * @param sharedBase 当前会话已单列的基础指令
   */
  private record Cut(String thread, int ordinal, long bytes, String sharedBase) {}

  /** 历史角色和工具载荷分别计数。 */
  private enum Kind {
    INSTRUCTIONS("fork_instructions"),
    USER("fork_user"),
    ASSISTANT("fork_assistant"),
    TOOL_INPUT("fork_tool_input"),
    TOOL_RESULT("fork_tool_result"),
    TOOL_DEFINITIONS("fork_tool_definitions");

    private final String key;

    Kind(String key) {
      this.key = key;
    }
  }

  /** 与正文构成条采用相同字符权重；不把加密正文或图片当作文本 Token。 */
  private static final class Counter {
    private long fragments;
    private long chars;
    private long tokens;

    void append(String text) {
      long ascii = 0;
      long punct = 0;
      long cjk = 0;
      for (int i = 0; i < text.length(); i++) {
        char c = text.charAt(i);
        if (c >= 32 && c <= 126) {
          ascii++;
          if (PUNCT.indexOf(c) >= 0) punct++;
        } else if (c >= 0x4e00 && c <= 0x9fff
            || c >= 0x3040 && c <= 0x30ff
            || c >= 0xac00 && c <= 0xd7af) cjk++;
      }
      fragments++;
      chars += text.codePointCount(0, text.length());
      tokens +=
          Math.max(
              1,
              Math.round(
                  cjk / 1.8
                      + punct / 3.0
                      + (ascii - punct) / 4.0
                      + (text.length() - ascii - cjk) / 2.5));
    }

    String encoded() {
      return fragments + ":" + chars + ":" + tokens;
    }
  }

  /** 只读取可信分叉字节范围，不访问父会话后续正文。 */
  private static final class BoundedInput extends FilterInputStream {
    private long remaining;

    BoundedInput(InputStream source, long bytes) {
      super(source);
      remaining = bytes;
    }

    @Override
    public int read() throws IOException {
      if (remaining == 0) return -1;
      int value = in.read();
      if (value >= 0) remaining--;
      return value;
    }

    @Override
    public int read(byte[] data, int offset, int length) throws IOException {
      if (length == 0) return 0;
      if (remaining == 0) return -1;
      int count = in.read(data, offset, (int) Math.min(length, remaining));
      if (count > 0) remaining -= count;
      return count;
    }
  }
}
