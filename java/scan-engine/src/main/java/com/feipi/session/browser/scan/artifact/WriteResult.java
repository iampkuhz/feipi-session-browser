package com.feipi.session.browser.scan.artifact;

import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.nio.file.Path;

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
    /* 数据文件的绝对路径。 */
    @NotNull Path dataPath,

    /* meta 文件的绝对路径。 */
    @NotNull Path metaPath,

    /* 数据文件内容的 SHA-256 十六进制摘要。 */
    @NotBlank String contentHash,

    /* 数据文件内容的字节长度。 */
    @PositiveOrZero long contentSize,

    /* 写入状态描述。 */
    @NotBlank String status) {

  /**
   * 紧凑构造器，验证非空约束。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 {@code contentSize} 为负数时
   */
  public WriteResult {
    ValidationSupport.validateCanonicalConstructor(
        WriteResult.class, dataPath, metaPath, contentHash, contentSize, status);
  }
}
