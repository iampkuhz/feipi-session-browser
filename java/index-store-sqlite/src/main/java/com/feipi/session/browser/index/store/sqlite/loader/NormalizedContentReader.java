package com.feipi.session.browser.index.store.sqlite.loader;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Set;

/** 提供可重放的磁盘读取，仅保留当前有界单元及全局身份集合。 */
final class NormalizedContentReader implements NormalizedSessionContent {
  private static final ObjectMapper JSON =
      new ObjectMapper().configure(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS, true);
  private static final String FORMAT = "session-content.units.v1";
  private final Path path;
  private final NormalizedContentHeader header;
  private final String fingerprint;

  private NormalizedContentReader(Path path, NormalizedContentHeader header, String fingerprint) {
    this.path = path;
    this.header = header;
    this.fingerprint = fingerprint;
  }

  /** 先验证已提交制品的完整性，再开放内容读取。 */
  static NormalizedSessionContent open(Path path) throws IOException {
    try (JsonParser parser = JSON.createParser(path.toFile())) {
      require(parser.nextToken() == JsonToken.START_OBJECT, "expected object");
      boolean tagged = false;
      NormalizedContentHeader header = null;
      while (parser.nextToken() != JsonToken.END_OBJECT) {
        require(parser.currentToken() == JsonToken.FIELD_NAME, "truncated root");
        String name = parser.currentName();
        parser.nextToken();
        if ("storageFormat".equals(name)) {
          require(FORMAT.equals(parser.getValueAsString()), "unsupported storageFormat");
          tagged = true;
        } else if ("header".equals(name)) {
          header = NormalizedContentCodec.header(readMap(parser));
        } else {
          parser.skipChildren();
        }
      }
      require(parser.nextToken() == null, "trailing data");
      if (!tagged) {
        try (InputStream input = Files.newInputStream(path)) {
          return NormalizedSessionContent.fromArtifact(
              NormalizedArtifactLoader.fromMap(
                  JSON.readValue(input, new TypeReference<Map<String, Object>>() {})));
        }
      }
      String fingerprint = verifyMeta(path);
      require(header != null, "missing header");
      NormalizedContentReader content = new NormalizedContentReader(path, header, fingerprint);
      content.validate();
      return content;
    } catch (RuntimeException ex) {
      throw new IOException("invalid normalized content", ex);
    }
  }

  private static String verifyMeta(Path path) throws IOException {
    String name = path.getFileName().toString();
    Path meta = path.resolveSibling(name.substring(0, name.length() - 5) + ".meta.json");
    Map<String, Object> values;
    try (InputStream in = Files.newInputStream(meta)) {
      values = JSON.readValue(in, new TypeReference<Map<String, Object>>() {});
    }
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      long size = 0;
      try (InputStream in = Files.newInputStream(path)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) {
          digest.update(buffer, 0, count);
          size += count;
        }
      }
      require(
          Objects.equals(values.get("contentHash"), HexFormat.of().formatHex(digest.digest()))
              && values.get("contentSize") instanceof Number n
              && n.longValue() == size,
          "artifact hash/size mismatch");
      return Objects.toString(values.get("contentHash")) + ":" + size;
    } catch (NoSuchAlgorithmException ex) {
      throw new IOException(ex);
    }
  }

  @Override
  public NormalizedContentHeader header() {
    return header;
  }

  @Override
  public ContentCursor openCursor() throws IOException {
    require(fingerprint.equals(verifyMeta(path)), "artifact changed after verification");
    return new Cursor(path);
  }

  private void validate() throws IOException {
    Set<String> calls = new HashSet<>(), catalog = new HashSet<>(), required = new HashSet<>();
    Set<Integer> indexes = new HashSet<>();
    Set<String> toolIds = new HashSet<>();
    Map<String, Long> totals = new LinkedHashMap<>(), offsets = new HashMap<>();
    header.totals().keySet().forEach(k -> totals.put(k, 0L));
    long unitIndex = 0;
    try (ContentCursor cursor = openCursor()) {
      while (cursor.hasNext()) {
        NormalizedContentUnit unit = cursor.next();
        require(unit.unitIndex() == unitIndex++, "non-contiguous unitIndex");
        add(totals, "calls", unit.calls().size());
        add(totals, "toolExecutions", unit.toolExecutions().size());
        add(totals, "diagnostics", unit.diagnostics().size());
        add(totals, "sourceFiles", unit.sourceFiles().size());
        add(totals, "sourceUnitCatalog", unit.sourceUnitCatalog().size());
        for (NormalizedCall call : unit.calls()) {
          require(
              calls.add(call.callId()) && indexes.add(call.callIndex()), "duplicate call identity");
          call.parentCallId().ifPresent(required::add);
        }
        for (NormalizedToolExecution tool : unit.toolExecutions()) {
          require(toolIds.add(tool.toolCallId()), "duplicate tool identity");
          required.add(tool.declaredByCallId());
          tool.resultConsumedByCallId().ifPresent(required::add);
        }
        for (var entry : unit.sourceUnitCatalog().entrySet()) {
          require(entry.getKey().equals(entry.getValue().unitKey()), "catalog key mismatch");
          require(catalog.add(entry.getKey()), "duplicate catalog key");
        }
        for (NormalizedSequenceChunk chunk : unit.sourceUnitSequences()) {
          require(chunk.offset() == offsets.getOrDefault(chunk.name(), 0L), "sequence gap");
          offsets.put(chunk.name(), chunk.offset() + chunk.keys().size());
          add(totals, "sourceUnitSequenceEntries", chunk.keys().size());
        }
      }
    }
    require(calls.containsAll(required), "unresolved strong call reference");
    require(totals.equals(header.totals()), "content totals mismatch");
  }

  private static void add(Map<String, Long> totals, String key, long amount) {
    totals.merge(key, amount, Math::addExact);
  }

  private static Map<String, Object> readMap(JsonParser parser) throws IOException {
    return JSON.readValue(parser, new TypeReference<Map<String, Object>>() {});
  }

  private static void require(boolean valid, String message) throws IOException {
    if (!valid) throw new IOException(message);
  }

  /** 持有一次独立流式遍历及其文件描述符，并负责关闭资源。 */
  private static final class Cursor implements ContentCursor {
    private final JsonParser parser;
    private boolean closed;
    private JsonToken next;

    Cursor(Path path) throws IOException {
      parser = JSON.createParser(path.toFile());
      try {
        require(parser.nextToken() == JsonToken.START_OBJECT, "expected root");
        while (parser.nextToken() != JsonToken.END_OBJECT) {
          require(parser.currentToken() == JsonToken.FIELD_NAME, "truncated root");
          String name = parser.currentName();
          parser.nextToken();
          if ("units".equals(name)) {
            require(parser.currentToken() == JsonToken.START_ARRAY, "expected units array");
            next = parser.nextToken();
            return;
          }
          parser.skipChildren();
        }
        throw new IOException("missing units");
      } catch (IOException | RuntimeException ex) {
        parser.close();
        throw ex;
      }
    }

    @Override
    public boolean hasNext() throws IOException {
      if (closed) return false;
      if (next == JsonToken.END_ARRAY) {
        close();
        return false;
      }
      require(next == JsonToken.START_OBJECT, "truncated units");
      return true;
    }

    @Override
    public NormalizedContentUnit next() throws IOException {
      if (!hasNext()) throw new NoSuchElementException();
      try {
        NormalizedContentUnit unit = NormalizedContentCodec.unit(readMap(parser));
        next = parser.nextToken();
        return unit;
      } catch (IOException | RuntimeException ex) {
        close();
        throw ex;
      }
    }

    @Override
    public void close() throws IOException {
      closed = true;
      parser.close();
    }
  }
}
