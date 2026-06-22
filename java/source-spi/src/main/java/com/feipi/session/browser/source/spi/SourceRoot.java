package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.nio.file.Path;
import java.util.Objects;

/**
 * 源根目录安全检查结果。
 *
 * <p>描述一个源根目录在解析时的安全属性。用于检测符号链接跟踪、 路径逃逸和只读状态，防止越权访问。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code rootPath} 不得为 null。
 *   <li>{@code resolvedPath} 不得为 null。
 * </ul>
 *
 * @param rootPath 声明的根目录路径
 * @param resolvedPath 经过符号链接解析后的实际路径
 * @param symlinkFollowed 解析过程中是否跟踪了符号链接
 * @param pathEscapeDetected 是否检测到路径逃逸（解析后路径不在根目录内）
 * @param readOnly 根目录是否为只读
 */
@DomainModel
public record SourceRoot(
    @CoreField Path rootPath,
    @CoreField Path resolvedPath,
    @CoreField boolean symlinkFollowed,
    @CoreField boolean pathEscapeDetected,
    @CoreField boolean readOnly) {

  /**
   * 紧凑构造器，验证源根不变量。
   *
   * @throws NullPointerException 当路径字段为 null 时
   */
  public SourceRoot {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");
    Objects.requireNonNull(resolvedPath, "resolvedPath 不得为 null");
  }

  /**
   * 判断该源根是否安全可用。
   *
   * <p>安全条件：未检测到路径逃逸。符号链接和只读状态不阻止使用， 但路径逃逸表示存在越权访问风险。
   *
   * @return 无路径逃逸时返回 {@code true}
   */
  public boolean isSafe() {
    return !pathEscapeDetected;
  }
}
