package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import java.util.List;

/** 负责把源中性记录中的用量字段转换为归一化调用用量，并提供会话级聚合能力。 */
public final class TokenAccountant {

  /** 防止实例化。 */
  private TokenAccountant() {}

  /**
   * 从源中性记录提取 token 用量。
   *
   * @param record 源中性记录
   * @return 不可变的 token 用量实例
   */
  public static NormalizedCallUsage extractUsage(SourceRecord record) {
    if (record == null) {
      return NormalizedCallUsage.empty();
    }
    SourceRecordUsage usage = record.usage();
    return new NormalizedCallUsage(
        usage.inputTokens(),
        usage.cacheReadInputTokens(),
        usage.cacheCreationInputTokens(),
        usage.outputTokens(),
        usage.total());
  }

  /**
   * 聚合多个调用的 token 用量。
   *
   * @param usages token 用量列表，不得为 null
   * @return 聚合后的 token 用量实例
   */
  public static NormalizedCallUsage aggregate(List<NormalizedCallUsage> usages) {
    if (usages == null || usages.isEmpty()) {
      return NormalizedCallUsage.empty();
    }
    long fresh = 0;
    long cacheRead = 0;
    long cacheWrite = 0;
    long output = 0;
    for (NormalizedCallUsage u : usages) {
      fresh += u.fresh();
      cacheRead += u.cacheRead();
      cacheWrite += u.cacheWrite();
      output += u.output();
    }
    long total = fresh + cacheRead + cacheWrite + output;
    return new NormalizedCallUsage(fresh, cacheRead, cacheWrite, output, total);
  }
}
