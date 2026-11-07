package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.ToLongFunction;

/** 负责把源中性记录中的用量字段转换为归一化调用用量，并提供会话级聚合能力。 */
public final class TokenAccountant {

  /** 防止实例化。 */
  private TokenAccountant() {}

  /** 判断 Codex 新旧 usage 记录是否是响应末尾的调用边界。 */
  static boolean isUsageClosingFrame(String callId) {
    return callId.startsWith("token_count:") || isResponseUsageFrame(callId);
  }

  static boolean isResponseUsageFrame(String callId) {
    return callId.startsWith("token_usage_record:") || callId.startsWith("token_usage_ordinal:");
  }

  /** 子调用改用展示身份后，仍保留原始记录的边界证据。 */
  static Map<String, Object> modelCallEvidence(String sourceCallId) {
    if (sourceCallId.startsWith("token_usage_record:")) {
      return Map.of("modelCallEvidence", "response_usage");
    }
    if (sourceCallId.startsWith("token_count:")) {
      return Map.of("modelCallEvidence", "closing_counter");
    }
    return Map.of();
  }

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

  /** 按 Qoder 现有分量最大值规则保留贡献记录的证据，不从数值推断 provider 来源。 */
  static Map<String, String> maxUsageProvenance(List<SourceRecordUsage> usages) {
    Map<String, String> result = new LinkedHashMap<>();
    mergeComponentProvenance(
        usages, SourceRecordUsage::inputTokens, "freshInputTokenPrecision", result);
    mergeComponentProvenance(
        usages, SourceRecordUsage::cacheReadInputTokens, "cacheReadTokenPrecision", result);
    mergeComponentProvenance(
        usages, SourceRecordUsage::cacheCreationInputTokens, "cacheWriteTokenPrecision", result);
    mergeComponentProvenance(
        usages, SourceRecordUsage::outputTokens, "outputTokenPrecision", result);
    return Map.copyOf(result);
  }

  /** 相同最大值的来源冲突保留 mixed；无来源空零不覆盖同响应已显式测得的零。 */
  private static void mergeComponentProvenance(
      List<SourceRecordUsage> usages,
      ToLongFunction<SourceRecordUsage> value,
      String key,
      Map<String, String> result) {
    long maximum = usages.stream().mapToLong(value).max().orElse(0);
    Set<String> states = new LinkedHashSet<>();
    Set<String> methods = new LinkedHashSet<>();
    for (SourceRecordUsage usage : usages) {
      if (value.applyAsLong(usage) != maximum) continue;
      String state = usage.provenance().getOrDefault(key, "unknown");
      if (maximum == 0 && "unknown".equals(state)) continue;
      states.add(state);
      String method = usage.provenance().getOrDefault("tokenEstimationMethod", "");
      if (!method.isBlank()) methods.add(method);
      for (String flag :
          List.of("tokenContainsEstimated", "tokenContainsUnavailable", "tokenContainsUnknown")) {
        if (Boolean.parseBoolean(usage.provenance().get(flag))) result.put(flag, "true");
      }
    }
    if (states.isEmpty()) states.add("unknown");
    result.put(key, states.size() == 1 ? states.iterator().next() : "mixed");
    for (String state : states) {
      switch (state) {
        case "estimated" -> result.put("tokenContainsEstimated", "true");
        case "unavailable" -> result.put("tokenContainsUnavailable", "true");
        case "unknown" -> result.put("tokenContainsUnknown", "true");
        default -> {}
      }
    }
    if (!methods.isEmpty()) {
      String previous = result.getOrDefault("tokenEstimationMethod", "");
      if (!previous.isBlank()) methods.add(previous);
      result.put("tokenEstimationMethod", String.join(",", methods));
    }
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
