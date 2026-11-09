package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.source.common.JsonNodeSpool;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderResult;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

/** Codex 多遍解析的事件批次所有权；由调用者在完成全部遍历后关闭。 */
final class CodexEventBatch implements AutoCloseable {
  private final JsonlReaderResult result;
  private final JsonNodeSpool spool;

  private CodexEventBatch(JsonlReaderResult result, JsonNodeSpool spool) {
    this.result = result;
    this.spool = spool;
  }

  static CodexEventBatch read(JsonlReader reader, Path path) throws IOException {
    var spool = new JsonNodeSpool();
    boolean complete = false;
    try {
      var result = CodexEventProjection.readTo(reader, path, spool);
      spool.seal();
      complete = true;
      return new CodexEventBatch(result, spool);
    } catch (java.io.UncheckedIOException failure) {
      throw new IOException("Codex 事件写入失败", failure);
    } finally {
      if (!complete) spool.close();
    }
  }

  List<JsonNode> events() {
    return spool;
  }

  JsonlReaderResult result() {
    return result;
  }

  @Override
  public void close() throws IOException {
    spool.close();
  }
}
