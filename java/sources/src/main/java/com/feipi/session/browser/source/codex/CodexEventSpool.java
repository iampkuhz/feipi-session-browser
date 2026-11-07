package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.AbstractList;
import java.util.Arrays;
import java.util.Objects;

/** 仅保存顺序 JSON 和紧凑 long 偏移，不缓存 JsonNode 或正文；关闭时删除 owner-only 临时目录。 */
final class CodexEventSpool extends AbstractList<JsonNode> implements AutoCloseable {
  private final ObjectMapper mapper =
      new ObjectMapper().enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
  private final Path directory;
  private final Path data;
  private final CountingOutput output;
  private long[] offsets = new long[1024];
  private int count;
  private long length;
  private FileChannel channel;
  private boolean closed;

  CodexEventSpool() throws IOException {
    directory =
        Files.createTempDirectory(
            "feipi-codex-events-",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
    data = directory.resolve("events");
    try {
      output = new CountingOutput(new BufferedOutputStream(Files.newOutputStream(data)));
    } catch (IOException failure) {
      Files.deleteIfExists(data);
      Files.deleteIfExists(directory);
      throw failure;
    }
  }

  @Override
  public boolean add(JsonNode event) {
    if (closed || channel != null) throw new IllegalStateException("事件批次不可追加");
    try {
      if (count == offsets.length) offsets = Arrays.copyOf(offsets, Math.multiplyExact(count, 2));
      long start = output.count;
      try (var generator = mapper.getFactory().createGenerator(output)) {
        generator.disable(JsonGenerator.Feature.AUTO_CLOSE_TARGET);
        mapper.writeTree(generator, event);
      }
      output.write('\n');
      offsets[count++] = start;
      return true;
    } catch (IOException failure) {
      throw new UncheckedIOException(failure);
    }
  }

  void seal() throws IOException {
    output.close();
    length = output.count;
    channel = FileChannel.open(data, StandardOpenOption.READ);
  }

  @Override
  public JsonNode get(int index) {
    Objects.checkIndex(index, count);
    if (closed || channel == null) throw new IllegalStateException("事件批次尚未完成或已关闭");
    long start = offsets[index];
    long end = index + 1 < count ? offsets[index + 1] : length;
    try (var input = new SliceInput(channel, start, end)) {
      JsonNode event = mapper.readTree(input);
      if (event == null || !event.isObject()) throw new IOException("事件 spool 记录损坏");
      return event;
    } catch (IOException failure) {
      throw new UncheckedIOException(failure);
    }
  }

  @Override
  public int size() {
    return count;
  }

  @Override
  public void clear() {
    // reader 仅在全局 INVALID_UTF8 时回滚；已写正文不再暴露，随批次关闭清理。
    count = 0;
  }

  Path directory() {
    return directory;
  }

  @Override
  public void close() throws IOException {
    if (closed) return;
    closed = true;
    try {
      output.close();
    } finally {
      try {
        if (channel != null) channel.close();
      } finally {
        try {
          Files.deleteIfExists(data);
        } finally {
          Files.deleteIfExists(directory);
        }
      }
    }
  }

  /** 顺序写入计数在缓冲层之上，偏移不依赖 flush 时机。 */
  private static final class CountingOutput extends OutputStream {
    private final OutputStream target;
    private long count;

    private CountingOutput(OutputStream target) {
      this.target = target;
    }

    @Override
    public void write(int value) throws IOException {
      target.write(value);
      count++;
    }

    @Override
    public void write(byte[] bytes, int offset, int length) throws IOException {
      target.write(bytes, offset, length);
      count += length;
    }

    @Override
    public void flush() throws IOException {
      target.flush();
    }

    @Override
    public void close() throws IOException {
      target.close();
    }
  }

  /** 每次重放有独立位置，关闭切片不关闭批次拥有的 channel。 */
  private static final class SliceInput extends InputStream {
    private final FileChannel channel;
    private final long end;
    private long position;
    private final byte[] single = new byte[1];

    private SliceInput(FileChannel channel, long start, long end) {
      this.channel = channel;
      this.position = start;
      this.end = end;
    }

    @Override
    public int read() throws IOException {
      int size = read(single, 0, 1);
      return size < 0 ? -1 : single[0] & 255;
    }

    @Override
    public int read(byte[] bytes, int offset, int length) throws IOException {
      Objects.checkFromIndexSize(offset, length, bytes.length);
      if (length == 0) return 0;
      if (position == end) return -1;
      int size =
          channel.read(
              ByteBuffer.wrap(bytes, offset, (int) Math.min(length, end - position)), position);
      if (size < 0) throw new IOException("事件 spool 提前结束");
      position += size;
      return size;
    }
  }
}
