package com.feipi.session.browser.domain.source;

import java.io.IOException;
import java.util.List;

/**
 * 可重放的源中性记录序列；调用者拥有序列，借用者仅关闭自己的游标。
 *
 * <p>关闭序列须幂等，并使新游标及已有游标的后续读取明确失败。实现不得把读取错误视为 EOF。
 */
public interface SourceRecordSequence extends AutoCloseable {
  /**
   * 返回完整记录总数，包括保留的 neutral 与 fallback 表示；关闭后仍可读取此元信息。
   *
   * @return 非负记录数
   */
  long recordCount();

  /**
   * 从第零条记录打开独立游标，不共享其他游标的遍历位置。
   *
   * @return 独立读取游标
   * @throws IOException 序列已关闭或无法打开时
   */
  default RecordCursor openCursor() throws IOException {
    return openCursor(0);
  }

  /**
   * 从指定序列位置独立重放；位置不是 provider 的 eventIndex，等于总数时返回空游标。
   *
   * @param ordinal 从零开始的位置，范围为零至记录总数（含两端）
   * @return 独立读取游标
   * @throws IllegalArgumentException 位置越界时
   * @throws IOException 序列已关闭或无法打开时
   */
  RecordCursor openCursor(long ordinal) throws IOException;

  /**
   * 幂等释放序列拥有的资源；所有借用游标应先关闭。
   *
   * @throws IOException 资源释放失败时
   */
  @Override
  void close() throws IOException;

  /**
   * 将已有记录列表防御复制为内存序列；不承诺输入规模无关的内存占用。
   *
   * @param records 非 null 记录列表，元素不得为 null
   * @return 拥有独立关闭状态的不可变列表适配器
   */
  static SourceRecordSequence fromList(List<SourceRecord> records) {
    return new ListSourceRecordSequence(records);
  }

  /** 独立的记录读取游标；关闭游标不转移或释放序列所有权。 */
  interface RecordCursor extends AutoCloseable {
    /**
     * 判断是否有下一条记录，失败不得视为空序列。
     *
     * @return 是否还有记录
     * @throws IOException 游标或序列已关闭，或读取失败时
     */
    boolean hasNext() throws IOException;

    /**
     * 读取下一条完整记录，保持原顺序与重复表示。
     *
     * @return 下一条记录
     * @throws java.util.NoSuchElementException 已到序列末尾时
     * @throws IOException 游标或序列已关闭，或读取失败时
     */
    SourceRecord next() throws IOException;

    /**
     * 幂等释放当前游标资源，不关闭所属序列。
     *
     * @throws IOException 资源释放失败时
     */
    @Override
    void close() throws IOException;
  }
}
