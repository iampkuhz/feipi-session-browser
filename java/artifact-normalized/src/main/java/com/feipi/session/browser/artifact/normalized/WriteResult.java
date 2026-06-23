package com.feipi.session.browser.artifact.normalized;

import java.nio.file.Path;
import java.util.Objects;

/**
 * 制品写入操作的正式结果。
 *
 * <p>包含写入后产生的数据文件路径、meta 文件路径、内容 hash、内容大小和写入状态。 调用方可据此进行后续校验或日志记录。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有字段不得为 null。
 *   <li>{@code contentSize} 必须非负。
 * </ul>
 *
 * @param dataPath 数据文件的绝对路径
 * @param metaPath meta 文件的绝对路径
 * @param contentHash 数据文件内容的 SHA-256 十六进制摘要
 * @param contentSize 数据文件内容的字节长度
 * @param status 写入状态描述
 */
public record WriteResult(
    Path dataPath, Path metaPath, String contentHash, long contentSize, String status) {

  /**
   * 紧凑构造器，验证非空约束。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 {@code contentSize} 为负数时
   */
  public WriteResult {
    Objects.requireNonNull(dataPath, "dataPath 不得为 null");
    Objects.requireNonNull(metaPath, "metaPath 不得为 null");
    Objects.requireNonNull(contentHash, "contentHash 不得为 null");
    if (contentSize < 0) {
      throw new IllegalArgumentException("contentSize 不得为负数; got " + contentSize);
    }
    Objects.requireNonNull(status, "status 不得为 null");
  }
}
