package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotNull;
import java.nio.file.Path;

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
 * @param rootPath 声明的根目录路径，不得为 null
 * @param resolvedPath 经过符号链接解析后的实际路径，不得为 null
 * @param symlinkFollowed 解析过程中是否跟踪了符号链接
 * @param pathEscapeDetected 是否检测到路径逃逸（解析后路径不在根目录内）
 * @param readOnly 根目录是否为只读
 */
@DomainModel
public record SourceRoot(
    /* 声明的根目录路径，不得为 null。 */
    @NotNull @CoreField Path rootPath,

    /* 经过符号链接解析后的实际路径，不得为 null。 */
    @NotNull @CoreField Path resolvedPath,

    /* 解析过程中是否跟踪了符号链接。 */
    @CoreField boolean symlinkFollowed,

    /* 是否检测到路径逃逸（解析后路径不在根目录内）。 */
    @CoreField boolean pathEscapeDetected,

    /* 根目录是否为只读。 */
    @CoreField boolean readOnly) {

  /** 紧凑构造器，校验约束。 */
  public SourceRoot {
    try {
      ValidationSupport.validateCanonicalConstructor(
          SourceRoot.class, rootPath, resolvedPath, symlinkFollowed, pathEscapeDetected, readOnly);
    } catch (ConstraintViolationException e) {
      translateNotNullViolations(e, new String[] {"rootPath", "resolvedPath"});
    }
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

  private static void translateNotNullViolations(
      ConstraintViolationException e, String[] notNullFields) {
    var violations = e.getConstraintViolations();
    for (String field : notNullFields) {
      for (var v : violations) {
        String path = v.getPropertyPath().toString();
        if ((path.equals(field) || path.endsWith("." + field))
            && v.getConstraintDescriptor().getAnnotation().annotationType() == NotNull.class) {
          throw new NullPointerException(field + " 不得为 null");
        }
      }
    }
    throw e;
  }
}
