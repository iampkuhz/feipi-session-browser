package com.feipi.session.browser.domain.source;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 源中性 token 用量。
 *
 * <p>用于承载 provider 解析阶段提取出的 token 分量；单位为 token，缺失或 unknown 时用 0 表示该分量未知/未提供，不表示 provider 真实用量一定为 0。
 *
 * @param inputTokens 新鲜输入 token 数，单位 token；未提供时为 0
 * @param cacheReadInputTokens 缓存读取输入 token 数，单位 token；未提供时为 0
 * @param cacheCreationInputTokens 缓存创建输入 token 数，单位 token；未提供时为 0
 * @param outputTokens 输出 token 数，单位 token；未提供时为 0
 */
@DomainModel
public record SourceRecordUsage(
    long inputTokens, long cacheReadInputTokens, long cacheCreationInputTokens, long outputTokens) {

  /** 校验 token 用量分量。 */
  public SourceRecordUsage {
    if (inputTokens < 0
        || cacheReadInputTokens < 0
        || cacheCreationInputTokens < 0
        || outputTokens < 0) {
      throw new IllegalArgumentException("token 用量不得为负数");
    }
  }

  /**
   * 返回空用量实例。
   *
   * @return 所有分量均为 0 的 token 用量
   */
  public static SourceRecordUsage empty() {
    return new SourceRecordUsage(0, 0, 0, 0);
  }

  /**
   * 返回总 token 数。
   *
   * @return 各 token 分量之和
   */
  public long total() {
    return inputTokens + cacheReadInputTokens + cacheCreationInputTokens + outputTokens;
  }
}
