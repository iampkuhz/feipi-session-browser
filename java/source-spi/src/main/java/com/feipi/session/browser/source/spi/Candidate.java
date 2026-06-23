package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.Map;
import java.util.Objects;

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
 * @param fingerprint 候选源文件的指纹
 * @param sessionKey 会话唯一标识键
 * @param projectKey 项目标识键（可为空字符串表示未分类）
 * @param metadata 发现阶段附加的元数据，不可变
 */
@DomainModel
public record Candidate(
    @CoreField SourceFingerprint fingerprint,
    @CoreField String sessionKey,
    @CoreField String projectKey,
    Map<String, String> metadata) {

  /** 候选项元数据大小上限。 */
  private static final int MAX_METADATA_SIZE = 100;

  /**
   * 紧凑构造器，验证候选项不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当会话键为空或元数据超限时
   */
  public Candidate {
    Objects.requireNonNull(fingerprint, "fingerprint 不得为 null");
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    if (sessionKey.isEmpty()) {
      throw new IllegalArgumentException("sessionKey 不得为空");
    }
    Objects.requireNonNull(projectKey, "projectKey 不得为 null");
    Map<String, String> metadataCopy =
        metadata == null ? Collections.emptyMap() : Map.copyOf(metadata);
    if (metadataCopy.size() > MAX_METADATA_SIZE) {
      throw new IllegalArgumentException("metadata size exceeds limit " + MAX_METADATA_SIZE);
    }
    metadata = metadataCopy;
  }

  /**
   * 返回候选项的源标识，委托给指纹。
   *
   * @return 源标识
   */
  public SourceId sourceId() {
    return fingerprint.sourceId();
  }
}
