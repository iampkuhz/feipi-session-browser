package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.SourceId;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** 扫描汇总 record 的共享校验与防御性拷贝。 */
final class ScanSummarySupport {

  private ScanSummarySupport() {}

  /** 校验计数不能为负。 */
  static void requireNonNegative(String name, long value) {
    if (value < 0) {
      throw new IllegalArgumentException(name + " 不得为负: " + value);
    }
  }

  /** 复制按 source 聚合的计数 map。 */
  static Map<SourceId, Integer> copyPerSourceCount(Map<SourceId, Integer> perSourceCount) {
    Objects.requireNonNull(perSourceCount, "perSourceCount 不得为 null");
    return Map.copyOf(perSourceCount);
  }

  /** 复制扫描问题列表。 */
  static List<ScanIssue> copyIssues(List<ScanIssue> issues) {
    Objects.requireNonNull(issues, "issues 不得为 null");
    return List.copyOf(issues);
  }
}
