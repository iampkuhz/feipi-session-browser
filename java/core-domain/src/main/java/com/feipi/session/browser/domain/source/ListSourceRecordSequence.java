package com.feipi.session.browser.domain.source;

import java.io.IOException;
import java.util.List;
import java.util.NoSuchElementException;

/** 小输入的不可变列表适配器；游标只保存自己的位置，不复制记录正文。 */
final class ListSourceRecordSequence implements SourceRecordSequence {
  private final List<SourceRecord> records;
  private boolean closed;

  /**
   * 防御复制记录列表并建立独立的所有者状态。
   *
   * @param records 非 null 记录列表，元素不得为 null
   */
  ListSourceRecordSequence(List<SourceRecord> records) {
    this.records = List.copyOf(records);
  }

  /** 返回构造时确定的完整记录数。 */
  @Override
  public long recordCount() {
    return records.size();
  }

  /**
   * 从合法位置打开独立游标；末位置对应空游标。
   *
   * @param ordinal 从零开始的序列位置
   * @return 独立游标
   * @throws IOException 所有者已关闭时
   */
  @Override
  public RecordCursor openCursor(long ordinal) throws IOException {
    ensureOpen();
    if (ordinal < 0 || ordinal > records.size()) {
      throw new IllegalArgumentException("record ordinal out of range: " + ordinal);
    }
    return new Cursor((int) ordinal);
  }

  /** 幂等关闭所有者；已有游标的后续读取也会拒绝。 */
  @Override
  public void close() {
    closed = true;
  }

  /**
   * 确认序列仍可读取。
   *
   * @throws IOException 所有者已关闭时
   */
  private void ensureOpen() throws IOException {
    if (closed) {
      throw new IOException("record sequence is closed");
    }
  }

  /** 只保存当前记录位置及关闭状态的借用游标。 */
  private final class Cursor implements RecordCursor {
    private int position;
    private boolean cursorClosed;

    /**
     * 保存本次独立遍历的起始位置。
     *
     * @param position 已校验的起始位置
     */
    private Cursor(int position) {
      this.position = position;
    }

    /** 检查所有者与游标状态，再判断当前位置是否到达末尾。 */
    @Override
    public boolean hasNext() throws IOException {
      ensureOpen();
      if (cursorClosed) {
        throw new IOException("record cursor is closed");
      }
      return position < records.size();
    }

    /** 返回当前位置记录并推进；EOF 不被混同为读取失败。 */
    @Override
    public SourceRecord next() throws IOException {
      if (!hasNext()) {
        throw new NoSuchElementException();
      }
      return records.get(position++);
    }

    /** 幂等关闭当前游标，不影响其他游标或所有者。 */
    @Override
    public void close() {
      cursorClosed = true;
    }
  }
}
