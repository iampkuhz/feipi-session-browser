package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.Map;

/**
 * 候选会话发现项。
 *
 * <p>表示源适配器从根目录中发现的一个待处理会话。每个候选项携带指纹用于 增量扫描判断，以及源标识和会话键用于后续归一化。
 *
 * <p>批次处理层接收候选项（而非原始根目录），因为候选项已包含发现阶段 产生的元数据，可直接驱动后续解析流程。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code fingerprint} 不得为 null，其 {@code locator} 应为稳定标识。
 *   <li>{@code sessionKey} 不得为 null 或空。
 *   <li>{@code metadata} 不可变，不含 null 值。
 * </ul>
 *
 * @param fingerprint 候选源文件的指纹，不得为 null
 * @param sessionKey 会话唯一标识键，不得为空
 * @param projectKey 项目标识键，可为空字符串表示未分类
 * @param metadata 发现阶段附加的元数据，不可变，大小上限 100
 */
@DomainModel
public record Candidate(
    /* 候选源文件的指纹，不得为 null。 */
    @NotNull @CoreField SourceFingerprint fingerprint,

    /* 会话唯一标识键，不得为空。 */
    @NotNull @NotBlank @CoreField String sessionKey,

    /* 项目标识键，可为空字符串表示未分类。 */
    @NotNull @CoreField String projectKey,

    /* 发现阶段附加的元数据，不可变，大小上限 100。 */
    Map<String, String> metadata) {

  /** 候选项元数据大小上限。 */
  private static final int MAX_METADATA_SIZE = 100;

  /**
   * 紧凑构造器，执行防御性拷贝并校验约束。
   *
   * @throws NullPointerException 当必填对象字段为 null 时
   * @throws IllegalArgumentException 当会话键为空或元数据超限时
   */
  public Candidate {
    metadata = ImmutableCopies.boundedMapOrEmpty(metadata, MAX_METADATA_SIZE, "metadata");
    try {
      ValidationSupport.validateCanonicalConstructor(
          Candidate.class, fingerprint, sessionKey, projectKey, metadata);
    } catch (ConstraintViolationException e) {
      translateValidation(e);
    }
  }

  /**
   * 返回候选项的源标识，委托给指纹。
   *
   * @return 源标识
   */
  public SourceId sourceId() {
    return fingerprint.sourceId();
  }

  private static void translateValidation(ConstraintViolationException e) {
    var violations = e.getConstraintViolations();
    for (var v : violations) {
      String path = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotNull.class) {
        String field = path.contains(".") ? path.substring(path.lastIndexOf('.') + 1) : path;
        throw new NullPointerException(field + " 不得为 null");
      }
    }
    for (var v : violations) {
      String path = v.getPropertyPath().toString();
      Class<? extends java.lang.annotation.Annotation> type =
          v.getConstraintDescriptor().getAnnotation().annotationType();
      if (type == NotBlank.class) {
        String field = path.contains(".") ? path.substring(path.lastIndexOf('.') + 1) : path;
        throw new IllegalArgumentException(field + " 不得为空");
      }
    }
    throw e;
  }
}
