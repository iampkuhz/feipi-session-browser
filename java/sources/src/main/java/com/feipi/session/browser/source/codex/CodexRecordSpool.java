package com.feipi.session.browser.source.codex;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import java.io.BufferedOutputStream;
import java.io.DataOutputStream;
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
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.zip.CRC32;
import java.util.zip.CheckedInputStream;
import java.util.zip.CheckedOutputStream;

/** owner-only mapped-record 序列；正文及 long 偏移均写磁盘，每个 cursor 独立重放。 */
final class CodexRecordSpool extends AbstractList<SourceRecord> implements SourceRecordSequence {
  private final Path directory;
  private final Path dataPath;
  private final Path indexPath;
  private final CountOutput data;
  private final DataOutputStream writer;
  private final DataOutputStream indexWriter;
  private final byte[] scratch = new byte[8192];
  private final CRC32 checksum = new CRC32();
  private FileChannel dataChannel;
  private FileChannel indexChannel;
  private long count;
  private long length;
  private boolean sealed;
  private boolean closed;

  CodexRecordSpool() throws IOException {
    directory =
        Files.createTempDirectory(
            "feipi-codex-records-",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
    dataPath = directory.resolve("data");
    indexPath = directory.resolve("index");
    data = openData();
    writer = new DataOutputStream(new CheckedOutputStream(data, checksum));
    try {
      indexWriter =
          new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(indexPath)));
    } catch (IOException failure) {
      try {
        writer.close();
      } catch (IOException close) {
        failure.addSuppressed(close);
      }
      removeFailedFiles(failure);
      throw failure;
    }
  }

  private CountOutput openData() throws IOException {
    try {
      return new CountOutput(new BufferedOutputStream(Files.newOutputStream(dataPath)));
    } catch (IOException failure) {
      removeFailedFiles(failure);
      throw failure;
    }
  }

  private void removeFailedFiles(IOException failure) {
    for (Path path : List.of(dataPath, indexPath, directory)) {
      try {
        Files.deleteIfExists(path);
      } catch (IOException close) {
        failure.addSuppressed(close);
      }
    }
  }

  @Override
  public boolean add(SourceRecord record) {
    if (closed || sealed) throw new IllegalStateException("记录序列不可追加");
    try {
      long start = data.count;
      checksum.reset();
      CodexRecordCodec.write(writer, record, scratch);
      long expectedChecksum = checksum.getValue();
      writer.writeLong(expectedChecksum);
      indexWriter.writeLong(start);
      count++;
      return true;
    } catch (IOException failure) {
      throw new UncheckedIOException(failure);
    }
  }

  void seal() throws IOException {
    ensureOpen();
    if (sealed) return;
    writer.close();
    indexWriter.close();
    length = data.count;
    dataChannel = FileChannel.open(dataPath, StandardOpenOption.READ);
    indexChannel = FileChannel.open(indexPath, StandardOpenOption.READ);
    sealed = true;
  }

  long payloadBytes() {
    return data.count;
  }

  Path directory() {
    return directory;
  }

  @Override
  public long recordCount() {
    return count;
  }

  @Override
  public int size() {
    return Math.toIntExact(recordCount());
  }

  @Override
  public SourceRecord get(int ordinal) {
    try {
      return read(ordinal);
    } catch (IOException failure) {
      throw new UncheckedIOException(failure);
    }
  }

  private void ensureOpen() throws IOException {
    if (closed) throw new IOException("记录序列已关闭");
  }

  private long offset(long ordinal) throws IOException {
    return readLong(indexChannel, Math.multiplyExact(ordinal, Long.BYTES));
  }

  private static long readLong(FileChannel channel, long position) throws IOException {
    ByteBuffer buffer = ByteBuffer.allocate(Long.BYTES);
    while (buffer.hasRemaining()) {
      int read = channel.read(buffer, position + buffer.position());
      if (read < 0) throw new IOException("记录字段提前结束");
    }
    buffer.flip();
    return buffer.getLong();
  }

  private void validateLengths() throws IOException {
    if (dataChannel.size() != length
        || indexChannel.size() != Math.multiplyExact(count, Long.BYTES))
      throw new IOException("sealed 记录序列长度变化");
  }

  private SourceRecord read(long ordinal) throws IOException {
    ensureOpen();
    if (!sealed) throw new IOException("记录序列尚未完成");
    if (ordinal < 0 || ordinal >= count) throw new IndexOutOfBoundsException("record ordinal");
    validateLengths();
    long start = offset(ordinal), end = ordinal + 1 < count ? offset(ordinal + 1) : length;
    if (start < 0 || end < start || end - start < Long.BYTES || end > length)
      throw new IOException("记录索引损坏");
    long expectedChecksum = readLong(dataChannel, end - Long.BYTES);
    var actualChecksum = new CRC32();
    try (var input =
        new CheckedInputStream(new Slice(dataChannel, start, end - Long.BYTES), actualChecksum)) {
      SourceRecord record = CodexRecordCodec.read(input, end - start - Long.BYTES);
      if (actualChecksum.getValue() != expectedChecksum) throw new IOException("记录校验和损坏");
      return record;
    }
  }

  @Override
  public RecordCursor openCursor() throws IOException {
    return openCursor(0);
  }

  @Override
  public RecordCursor openCursor(long ordinal) throws IOException {
    ensureOpen();
    if (!sealed) throw new IOException("记录序列尚未完成");
    if (ordinal < 0 || ordinal > count) throw new IllegalArgumentException("record ordinal");
    validateLengths();
    return new RecordCursor() {
      private long next = ordinal;
      private boolean cursorClosed;

      private void check() throws IOException {
        ensureOpen();
        validateLengths();
        if (cursorClosed) throw new IOException("记录游标已关闭");
      }

      @Override
      public boolean hasNext() throws IOException {
        check();
        return next < count;
      }

      @Override
      public SourceRecord next() throws IOException {
        check();
        if (next == count) throw new NoSuchElementException();
        SourceRecord record = read(next);
        next++;
        return record;
      }

      @Override
      public void close() {
        cursorClosed = true;
      }
    };
  }

  @Override
  public void close() throws IOException {
    if (closed) return;
    closed = true;
    IOException failure = null;
    var dataInput = dataChannel;
    var indexInput = indexChannel;
    try (writer;
        indexWriter;
        dataInput;
        indexInput) {
      // 真实 owner 在所有路径关闭四个句柄，TWR 保留后续关闭异常为 suppressed。
    } catch (Exception close) {
      failure = new IOException("记录序列关闭失败", close);
    }
    for (Path path : List.of(dataPath, indexPath, directory)) {
      try {
        Files.deleteIfExists(path);
      } catch (IOException close) {
        if (failure == null) failure = close;
        else failure.addSuppressed(close);
      }
    }
    if (failure != null) throw failure;
  }

  /** 缓冲层之上的字节计数，不建立整 record byte[]。 */
  private static final class CountOutput extends OutputStream {
    private final OutputStream output;
    private long count;

    private CountOutput(OutputStream output) {
      this.output = output;
    }

    @Override
    public void write(int value) throws IOException {
      output.write(value);
      count++;
    }

    @Override
    public void write(byte[] bytes, int offset, int size) throws IOException {
      output.write(bytes, offset, size);
      count += size;
    }

    @Override
    public void flush() throws IOException {
      output.flush();
    }

    @Override
    public void close() throws IOException {
      output.close();
    }
  }

  /** 独立 positional 读取，不关闭 owner channel。 */
  private static final class Slice extends InputStream {
    private final FileChannel channel;
    private final long end;
    private long position;
    private final byte[] single = new byte[1];

    private Slice(FileChannel channel, long start, long end) {
      this.channel = channel;
      position = start;
      this.end = end;
    }

    @Override
    public int read() throws IOException {
      int size = read(single, 0, 1);
      return size < 0 ? -1 : single[0] & 255;
    }

    @Override
    public int read(byte[] bytes, int offset, int size) throws IOException {
      Objects.checkFromIndexSize(offset, size, bytes.length);
      if (size == 0) return 0;
      if (position == end) return -1;
      int read =
          channel.read(
              ByteBuffer.wrap(bytes, offset, (int) Math.min(size, end - position)), position);
      if (read < 0) throw new IOException("记录正文提前结束");
      position += read;
      return read;
    }
  }
}
