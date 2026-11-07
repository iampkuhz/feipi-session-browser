package com.feipi.session.browser.domain.normalized;

import java.util.Map;

/**
 * 完整逻辑会话的元数据；总数覆盖所有有界内容单元，不表示某个单元的局部计数。
 *
 * @param schemaVersion 归一化领域模型的版本号，不是物理存储格式标记
 * @param agent 产生该逻辑会话的来源平台
 * @param session 完整会话元数据，不随内容单元重复计数
 * @param totals 六项跨单元总数，其中来源序列计数为所有键的数量之和
 */
public record NormalizedContentHeader(
    String schemaVersion,
    NormalizedAgent agent,
    NormalizedSessionMetadata session,
    Map<String, Long> totals) {
  /** 验证归一化版本及六项非负会话总数，并保存总数的不可变副本。 */
  public NormalizedContentHeader {
    if (!NormalizedConstants.SCHEMA_VERSION.equals(schemaVersion)) {
      throw new IllegalArgumentException("unsupported normalized schema: " + schemaVersion);
    }
    java.util.Objects.requireNonNull(agent, "agent");
    java.util.Objects.requireNonNull(session, "session");
    totals = Map.copyOf(totals);
    if (!totals
            .keySet()
            .equals(
                java.util.Set.of(
                    "calls",
                    "toolExecutions",
                    "diagnostics",
                    "sourceFiles",
                    "sourceUnitCatalog",
                    "sourceUnitSequenceEntries"))
        || totals.values().stream().anyMatch(value -> value < 0)) {
      throw new IllegalArgumentException("content totals require six nonnegative counts");
    }
  }
}
