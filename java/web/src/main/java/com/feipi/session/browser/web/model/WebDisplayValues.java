package com.feipi.session.browser.web.model;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

/** Web 展示层共享的格式化与计算辅助方法。 */
public final class WebDisplayValues {

  private static final ZoneId DISPLAY_ZONE = ZoneId.of("Asia/Shanghai");

  private WebDisplayValues() {}

  /** 解析 ISO 时间到展示日期；空值或非法值返回 null。 */
  public static LocalDate parseDate(String value) {
    if (value == null || value.isEmpty()) {
      return null;
    }
    try {
      return Instant.parse(value.replace("Z", "+00:00")).atZone(DISPLAY_ZONE).toLocalDate();
    } catch (RuntimeException ignored) {
      return null;
    }
  }

  /** 按粒度构建 day/week/month bucket label。 */
  public static String bucketLabel(LocalDate date, String grain) {
    if ("month".equals(grain)) {
      return date.getYear()
          + "-"
          + String.format(java.util.Locale.ROOT, "%02d", date.getMonthValue());
    }
    if ("week".equals(grain)) {
      return date.minusDays(date.getDayOfWeek().getValue() - 1L).toString();
    }
    return date.toString();
  }

  /** 计算百分比分母份额，分母非正时返回 0。 */
  public static double share(long value, long total) {
    return total <= 0 ? 0.0 : value * 100.0 / total;
  }

  /** 返回 agent 展示名。 */
  public static String agentDisplay(String dbAgent) {
    if (dbAgent == null || dbAgent.isEmpty()) {
      return "Unknown";
    }
    return switch (dbAgent) {
      case "claude_code" -> "Claude Code";
      case "qoder" -> "Qoder";
      case "codex" -> "Codex";
      default -> dbAgent;
    };
  }
}
