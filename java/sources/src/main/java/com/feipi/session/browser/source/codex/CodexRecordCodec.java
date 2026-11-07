package com.feipi.session.browser.source.codex;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalLong;

/** 显式逐字段编码；UTF16 code units 保留未配对 surrogate，解码始终执行领域构造器校验。 */
final class CodexRecordCodec {
  private static final int MAGIC = 0x43525331;

  private CodexRecordCodec() {}

  static void write(DataOutputStream out, SourceRecord r, byte[] scratch) throws IOException {
    var w = new Writer(out, scratch);
    out.writeInt(MAGIC);
    w.string(r.locator());
    out.writeInt(r.eventIndex());
    w.string(r.eventType());
    w.optional(r.callId());
    w.optional(r.model());
    w.optional(r.timestamp());
    w.optional(r.turnId());
    var usage = r.usage();
    out.writeLong(usage.inputTokens());
    out.writeLong(usage.cacheReadInputTokens());
    out.writeLong(usage.cacheCreationInputTokens());
    out.writeLong(usage.outputTokens());
    out.writeInt(usage.provenance().size());
    for (var entry : usage.provenance().entrySet()) {
      w.string(entry.getKey());
      w.string(entry.getValue());
    }
    out.writeInt(r.toolCalls().size());
    for (var tool : r.toolCalls()) {
      w.string(tool.toolCallId());
      w.string(tool.name());
      w.string(tool.input());
    }
    w.optional(r.toolUseId());
    w.optional(r.toolName());
    w.optional(r.toolError());
    var relation = r.relation();
    w.optional(relation.subagentId());
    w.optional(relation.parentThreadId());
    w.optional(relation.parentToolCallId());
    w.optional(relation.parentCallId());
    w.optional(relation.parentToolName());
    w.string(r.content());
    w.optional(r.responseMessageId());
    w.optional(r.responseStopReason());
    var timing = r.timing();
    w.string(timing.kind());
    w.string(timing.turnId());
    w.optional(timing.startedAt());
    w.optional(timing.completedAt());
    w.optionalLong(timing.durationMs());
    w.optionalLong(timing.modelDurationMs());
    w.optionalLong(timing.toolDurationMs());
    w.string(timing.eventId());
    out.writeBoolean(r.metaContext());
    w.optional(r.messageRole());
  }

  static SourceRecord read(InputStream stream, long bytes) throws IOException {
    try {
      var reader = new Reader(stream, bytes);
      SourceRecord record = reader.record();
      if (reader.remaining != 0) throw new IOException("记录包含额外字节");
      return record;
    } catch (RuntimeException invalid) {
      throw new IOException("记录字段校验失败", invalid);
    }
  }

  /**
   * 复用固定缓冲区逐字符串输出，不复制整条记录或全文件。
   *
   * @param out 当前记录输出流
   * @param scratch 复用的固定字节缓冲区
   */
  private record Writer(DataOutputStream out, byte[] scratch) {
    private void string(String value) throws IOException {
      out.writeInt(value.length());
      for (int start = 0; start < value.length(); ) {
        int count = Math.min(scratch.length / 2, value.length() - start);
        for (int index = 0; index < count; index++) {
          char ch = value.charAt(start + index);
          scratch[index * 2] = (byte) (ch >>> 8);
          scratch[index * 2 + 1] = (byte) ch;
        }
        out.write(scratch, 0, count * 2);
        start += count;
      }
    }

    private void optional(Optional<String> value) throws IOException {
      out.writeBoolean(value.isPresent());
      if (value.isPresent()) string(value.orElseThrow());
    }

    private void optionalLong(OptionalLong value) throws IOException {
      out.writeBoolean(value.isPresent());
      if (value.isPresent()) out.writeLong(value.orElseThrow());
    }
  }

  /** 所有长度先与本 frame 的剩余字节比较，损坏不是 EOF。 */
  private static final class Reader {
    private final DataInputStream in;
    private long remaining;

    private Reader(InputStream in, long remaining) {
      this.in = new DataInputStream(new BufferedInputStream(in));
      this.remaining = remaining;
    }

    private void consume(long bytes) throws IOException {
      if (bytes < 0 || bytes > remaining) throw new IOException("记录提前结束");
      remaining -= bytes;
    }

    private int integer() throws IOException {
      consume(4);
      return in.readInt();
    }

    private long number() throws IOException {
      consume(8);
      return in.readLong();
    }

    private boolean flag() throws IOException {
      consume(1);
      int value = in.readUnsignedByte();
      if (value > 1) throw new IOException("记录布尔字段损坏");
      return value == 1;
    }

    private String string() throws IOException {
      int count = integer();
      consume(2L * count);
      char[] chars = new char[count];
      for (int index = 0; index < count; index++) chars[index] = in.readChar();
      return new String(chars);
    }

    private Optional<String> optional() throws IOException {
      return flag() ? Optional.of(string()) : Optional.empty();
    }

    private OptionalLong optionalLong() throws IOException {
      return flag() ? OptionalLong.of(number()) : OptionalLong.empty();
    }

    private int count(int minimumBytes) throws IOException {
      int count = integer();
      if (count < 0 || (long) count * minimumBytes > remaining) throw new IOException("记录集合长度损坏");
      return count;
    }

    private SourceRecord record() throws IOException {
      if (integer() != MAGIC) throw new IOException("未知记录编码");
      String locator = string();
      int eventIndex = integer();
      String eventType = string();
      var call = optional();
      var model = optional();
      var timestamp = optional();
      var turn = optional();
      long input = number(), read = number(), write = number(), output = number();
      int precisionCount = count(8);
      Map<String, String> precision = new LinkedHashMap<>();
      for (int index = 0; index < precisionCount; index++) {
        if (precision.put(string(), string()) != null) throw new IOException("重复用量来源字段");
      }
      var usage = new SourceRecordUsage(input, read, write, output, precision);
      int toolCount = count(12);
      List<SourceToolCall> tools = new ArrayList<>();
      for (int index = 0; index < toolCount; index++)
        tools.add(new SourceToolCall(string(), string(), string()));
      var toolUseId = optional();
      var toolName = optional();
      var error = optional();
      var relation =
          new SourceRecordRelation(optional(), optional(), optional(), optional(), optional());
      String content = string();
      var message = optional();
      var stop = optional();
      var timing =
          new SourceTiming(
              string(),
              string(),
              optional(),
              optional(),
              optionalLong(),
              optionalLong(),
              optionalLong(),
              string());
      boolean meta = flag();
      var role = optional();
      return new SourceRecord(
          locator,
          eventIndex,
          eventType,
          call,
          model,
          timestamp,
          turn,
          usage,
          tools,
          toolUseId,
          toolName,
          error,
          relation,
          content,
          message,
          stop,
          timing,
          meta,
          role);
    }
  }
}
