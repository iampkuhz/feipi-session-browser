package com.feipi.session.browser.web.template;

import com.feipi.session.browser.web.model.SafeHtml;
import java.io.StringWriter;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 集中管理全部 presentation 显示格式化方法。
 *
 * <p>所有方法为纯静态函数，无副作用、无状态、不访问数据库或业务逻辑。 方法命名与 Python template_env.py 中注册的 Jinja2 filter
 * 一一对应，确保迁移行为一致。
 *
 * <p>校验放置：格式化函数对 null 输入返回安全默认值（空字符串或零值标签）， 不抛出异常。
 */
public final class DisplayFormatters {

  private static final int BYTES_PER_KIB = 1024;
  private static final int COMPACT_THOUSAND = 1_000;
  private static final int COMPACT_MILLION = 1_000_000;
  private static final int TRUNCATED_PATH_LENGTH = 40;
  private static final int SHORT_PATH_SEGMENTS = 3;
  private static final int DAYS_PER_MONTH = 30;
  private static final long SECONDS_PER_HOUR = 3600;
  private static final long SECONDS_PER_MINUTE = 60;

  private static final DateTimeFormatter LOCAL_TIME_FORMATTER =
      DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

  private static final Map<String, String> PRECISION_LABEL_MAP = buildPrecisionLabelMap();
  private static final List<String> KPI_ICON_COLORS =
      List.of("purple", "blue", "orange", "green", "red", "purple");

  private static final Map<String, String> DB_TO_SCOPE = buildDbToScopeMap();

  private DisplayFormatters() {}

  private static Map<String, String> buildPrecisionLabelMap() {
    Map<String, String> map = new LinkedHashMap<>();
    map.put("provider_reported", "实报");
    map.put("transcript_exact", "内容精确");
    map.put("exact", "精确");
    map.put("estimated", "估算");
    map.put("heuristic", "推断");
    map.put("residual", "未定位");
    map.put("unavailable", "不可用");
    return Map.copyOf(map);
  }

  private static Map<String, String> buildDbToScopeMap() {
    return Map.of("claude_code", "claude-code", "qoder", "qoder", "codex", "codex");
  }

  // ─── 数字格式化 ─────────────────────────────────────────────────

  /**
   * 格式化字节数为人类可读字符串。
   *
   * <p>例如 1024 → "1.0 KB"，1048576 → "1.0 MB"。null 或 0 返回 "0 B"。
   *
   * @param bytes 字节数，null 视为 0
   * @return 带单位的字节标签
   */
  public static String formatBytes(Number bytes) {
    if (bytes == null || bytes.longValue() == 0) {
      return "0 B";
    }
    long n = bytes.longValue();
    if (n < 0) {
      n = -n;
    }
    if (n < BYTES_PER_KIB) {
      return n + " B";
    }
    if (n < (long) BYTES_PER_KIB * BYTES_PER_KIB) {
      return String.format("%.1f KB", n / (double) BYTES_PER_KIB);
    }
    if (n < (long) BYTES_PER_KIB * BYTES_PER_KIB * BYTES_PER_KIB) {
      return String.format("%.1f MB", n / (double) (BYTES_PER_KIB * BYTES_PER_KIB));
    }
    return String.format("%.1f GB", n / (double) (BYTES_PER_KIB * BYTES_PER_KIB * BYTES_PER_KIB));
  }

  /**
   * 格式化 token 数为紧凑字符串。
   *
   * <p>例如 1500 → "1.5K"，2300000 → "2.3M"。null 返回 "0"。
   *
   * @param count token 数量，null 视为 0
   * @return 紧凑 token 标签
   */
  public static String formatCompactToken(Number count) {
    return formatCompactNum(count);
  }

  /**
   * 格式化数字为紧凑字符串（K/M 后缀）。
   *
   * <p>与 {@link #formatCompactToken(Number)} 行为一致，用于通用数字显示。
   *
   * @param number 数字，null 视为 0
   * @return 紧凑数字标签
   */
  public static String formatCompactNum(Number number) {
    if (number == null) {
      return "0";
    }
    long n = number.longValue();
    if (n >= COMPACT_MILLION) {
      return String.format("%.1fM", n / (double) COMPACT_MILLION);
    }
    if (n >= COMPACT_THOUSAND) {
      return String.format("%.1fK", n / (double) COMPACT_THOUSAND);
    }
    return String.valueOf(n);
  }

  /**
   * 格式化数字为一位小数字符串。
   *
   * @param number 数字，null 视为 0.0
   * @return 一位小数标签
   */
  public static String format1d(Number number) {
    if (number == null) {
      return "0.0";
    }
    return String.format("%.1f", number.doubleValue());
  }

  /**
   * 格式化持续时间为人类可读字符串。
   *
   * <p>例如 3661 → "1h 1min"，120 → "2min 0s"，30 → "30s"。
   *
   * @param seconds 持续秒数，null 视为 0
   * @return 持续时间标签
   */
  public static String formatDuration(Number seconds) {
    if (seconds == null) {
      return "0s";
    }
    long s = seconds.longValue();
    if (s >= SECONDS_PER_HOUR) {
      return (s / SECONDS_PER_HOUR) + "h " + ((s % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE) + "min";
    }
    if (s >= SECONDS_PER_MINUTE) {
      return (s / SECONDS_PER_MINUTE) + "min " + (s % SECONDS_PER_MINUTE) + "s";
    }
    return s + "s";
  }

  /**
   * 格式化覆盖率比例为整数百分比标签。
   *
   * <p>例如 0.856 → "86%"。null 返回 "—"。
   *
   * @param value 覆盖率，范围 [0, 1]，null 表示不可用
   * @return 百分比标签或破折号
   */
  public static String formatCoverage(Number value) {
    if (value == null) {
      return "—";
    }
    return Math.round(value.doubleValue() * 100) + "%";
  }

  // ─── 时间格式化 ─────────────────────────────────────────────────

  /**
   * 将 ISO 8601 时间戳转换为相对时间标签。
   *
   * <p>例如 "3h ago"、"2d ago"、"5mo ago"。null 或空返回空字符串。 解析失败时截断返回前 16 字符。
   *
   * @param isoStr ISO 8601 时间戳字符串
   * @return 相对时间标签
   */
  public static String relativeTime(String isoStr) {
    if (isoStr == null || isoStr.isEmpty()) {
      return "";
    }
    try {
      Instant then = Instant.parse(isoStr.replace("Z", "+00:00"));
      Instant now = Instant.now();
      long days = Duration.between(then, now).toDays();
      if (days > DAYS_PER_MONTH) {
        return (days / DAYS_PER_MONTH) + "mo ago";
      }
      if (days > 0) {
        return days + "d ago";
      }
      long hours = Duration.between(then, now).toHours();
      if (hours > 0) {
        return hours + "h ago";
      }
      long minutes = Duration.between(then, now).toMinutes();
      return minutes + "m ago";
    } catch (Exception e) {
      return isoStr.length() > 16 ? isoStr.substring(0, 16) : isoStr;
    }
  }

  /**
   * 将 UTC ISO 8601 时间戳转换为本地时间显示字符串。
   *
   * <p>格式为 "yyyy-MM-dd HH:mm:ss"，使用系统默认时区。 null 或空返回空字符串。解析失败时截断返回前 19 字符。
   *
   * @param isoStr ISO 8601 时间戳字符串
   * @return 本地时间格式化字符串
   */
  public static String toLocalTime(String isoStr) {
    if (isoStr == null || isoStr.isEmpty()) {
      return "";
    }
    try {
      Instant instant = Instant.parse(isoStr.replace("Z", "+00:00"));
      return instant.atZone(ZoneId.systemDefault()).format(LOCAL_TIME_FORMATTER);
    } catch (Exception e) {
      return isoStr.length() > 19 ? isoStr.substring(0, 19).replace('T', ' ') : isoStr;
    }
  }

  // ─── URL 编码 ──────────────────────────────────────────────────

  /**
   * URL 编码字符串（UTF-8）。
   *
   * @param value 原始字符串，null 视为空
   * @return URL 编码后的字符串
   */
  public static String urlEncode(String value) {
    if (value == null || value.isEmpty()) {
      return "";
    }
    return URLEncoder.encode(value, StandardCharsets.UTF_8);
  }

  /**
   * URL 解码字符串（UTF-8）。
   *
   * @param value 编码后的字符串，null 视为空
   * @return 解码后的原始字符串
   */
  public static String urlDecode(String value) {
    if (value == null || value.isEmpty()) {
      return "";
    }
    return URLDecoder.decode(value, StandardCharsets.UTF_8);
  }

  // ─── 路径格式化 ─────────────────────────────────────────────────

  /**
   * 截断长路径，保留首尾段。
   *
   * <p>路径长度超过 40 字符且段数大于 3 时，保留前 2 段和末尾 2 段，中间用 "…" 替代。
   *
   * @param path 原始路径，null 返回空字符串
   * @return 截断后的路径
   */
  public static String truncatePath(String path) {
    if (path == null || path.isEmpty()) {
      return "";
    }
    if (path.length() <= TRUNCATED_PATH_LENGTH) {
      return path;
    }
    String[] parts = path.replace('\\', '/').split("/");
    if (parts.length <= SHORT_PATH_SEGMENTS) {
      return path.substring(0, TRUNCATED_PATH_LENGTH) + "…";
    }
    return String.join("/", List.of(parts).subList(0, 2))
        + "/…/"
        + String.join("/", List.of(parts).subList(parts.length - 2, parts.length));
  }

  /**
   * 将用户主目录前缀替换为 {@code ~}。
   *
   * @param path 原始路径，null 返回空字符串
   * @return 替换后的显示路径
   */
  public static String displayPath(String path) {
    if (path == null || path.isEmpty()) {
      return "";
    }
    String home = Path.of(System.getProperty("user.home")).toString();
    if (path.equals(home)) {
      return "~";
    }
    String sep = java.io.File.separator;
    if (path.startsWith(home + sep)) {
      return "~" + path.substring(home.length());
    }
    return path;
  }

  /**
   * 缩短路径用于显示：先尝试仓库相对路径，再替换主目录，最后截断。
   *
   * @param path 原始路径，null 返回空字符串
   * @param repoRoot 仓库根路径，null 表示无仓库上下文
   * @return 缩短后的显示路径
   */
  public static String shortenPath(String path, String repoRoot) {
    if (path == null || path.isEmpty()) {
      return "";
    }
    if (repoRoot != null && !repoRoot.isEmpty()) {
      try {
        Path absPath = Path.of(path).toAbsolutePath().normalize();
        Path root = Path.of(repoRoot).toAbsolutePath().normalize();
        if (absPath.startsWith(root)) {
          String relative = root.relativize(absPath).toString();
          return truncatePath(relative);
        }
      } catch (Exception ignored) {
        // 路径解析失败时回退到 displayPath
      }
    }
    String displayed = displayPath(path);
    return truncatePath(displayed);
  }

  /**
   * 计算仓库相对路径。
   *
   * @param path 原始路径，null 返回空字符串
   * @param repoRoot 仓库根路径，null 返回原路径
   * @return 仓库相对路径，无法计算时返回原路径
   */
  public static String relativeToRepo(String path, String repoRoot) {
    if (path == null || path.isEmpty()) {
      return "";
    }
    if (repoRoot == null || repoRoot.isEmpty()) {
      return path;
    }
    try {
      Path absPath = Path.of(path).toAbsolutePath().normalize();
      Path root = Path.of(repoRoot).toAbsolutePath().normalize();
      if (absPath.startsWith(root)) {
        return root.relativize(absPath).toString();
      }
    } catch (Exception ignored) {
      // 路径解析失败时返回原路径
    }
    return path;
  }

  /**
   * 重新编号行号前缀。
   *
   * <p>将以 tab 分隔的行号前缀替换为从 1 开始的连续编号。 无行号前缀时返回原始文本。
   *
   * @param text 带行号的文本
   * @return 重新编号后的文本
   */
  public static String renumberLines(String text) {
    if (text == null || text.isEmpty()) {
      return text;
    }
    String[] lines = text.split("\n", -1);
    boolean hasLineNumbers = false;
    for (String line : lines) {
      if (line.matches("^\\d+\t.*")) {
        hasLineNumbers = true;
        break;
      }
    }
    if (!hasLineNumbers) {
      return text;
    }
    StringBuilder result = new StringBuilder();
    int num = 1;
    for (String line : lines) {
      if (result.length() > 0) {
        result.append('\n');
      }
      result.append(num++).append('\t').append(line.replaceFirst("^\\d+\t", ""));
    }
    return result.toString();
  }

  // ─── JSON 序列化 ────────────────────────────────────────────────

  /**
   * 将对象序列化为 JSON 并进行 HTML 转义。
   *
   * <p>适用于在 {@code <pre>} 标签内安全嵌入 JSON 数据。
   *
   * @param value 要序列化的对象，null 返回 "null"
   * @return HTML 转义后的 JSON 字符串
   */
  public static String tojsonSafeHtml(Object value) {
    if (value == null) {
      return "null";
    }
    return SimpleJson.toJson(value);
  }

  /**
   * 将对象序列化为 JSON 并 HTML 转义（等价于 {@link #tojsonSafeHtml(Object)}）。
   *
   * @param value 要序列化的对象
   * @return 安全 JSON 显示字符串
   */
  public static String safeJsonDisplay(Object value) {
    return tojsonSafeHtml(value);
  }

  /**
   * 将 JSON 值中的 file_path 字段替换为仓库相对路径后序列化并 HTML 转义。
   *
   * @param value JSON 可序列化对象
   * @param repoRoot 仓库根路径，null 表示不做路径替换
   * @return HTML 转义后的 JSON 字符串
   */
  public static String tojsonRepo(Object value, String repoRoot) {
    if (value == null) {
      return "null";
    }
    Object rewritten = rewriteFilePaths(value, repoRoot);
    return SimpleJson.toJson(rewritten);
  }

  /** 递归替换 JSON 结构中的 file_path 字段为仓库相对路径。 */
  @SuppressWarnings("unchecked")
  private static Object rewriteFilePaths(Object obj, String repoRoot) {
    if (obj instanceof Map<?, ?> map) {
      Map<String, Object> result = new LinkedHashMap<>();
      for (Map.Entry<?, ?> entry : map.entrySet()) {
        String key = String.valueOf(entry.getKey());
        Object val = entry.getValue();
        if ("file_path".equals(key) && val instanceof String strVal) {
          result.put(key, relativeToRepo(strVal, repoRoot));
        } else {
          result.put(key, rewriteFilePaths(val, repoRoot));
        }
      }
      return result;
    }
    if (obj instanceof List<?> list) {
      return list.stream().map(item -> rewriteFilePaths(item, repoRoot)).toList();
    }
    return obj;
  }

  // ─── 标签和 CSS 映射 ───────────────────────────────────────────

  /**
   * 将精度键映射为中文显示标签。
   *
   * @param precision 精度键，如 "provider_reported"
   * @return 中文标签，未知键返回原值，null 或空返回 "不可用"
   */
  public static String precisionLabel(String precision) {
    if (precision == null || precision.isEmpty()) {
      return "不可用";
    }
    return PRECISION_LABEL_MAP.getOrDefault(precision, precision);
  }

  /**
   * 映射 1-based KPI 索引到图标颜色 CSS 类名。
   *
   * @param index 1-based 索引
   * @return 颜色类名
   */
  public static String kpiIconColor(int index) {
    return KPI_ICON_COLORS.get((index - 1) % KPI_ICON_COLORS.size());
  }

  /**
   * 将数据库 agent 值转换为 URL scope 参数。
   *
   * <p>例如 "claude_code" → "claude-code"。
   *
   * @param dbAgent 数据库中的 agent 值
   * @return URL scope 参数
   */
  public static String dbAgentToScope(String dbAgent) {
    if (dbAgent == null || dbAgent.isEmpty()) {
      return dbAgent;
    }
    return DB_TO_SCOPE.getOrDefault(dbAgent, dbAgent);
  }

  /**
   * 将 URL scope 转换为 agent path 段。
   *
   * <p>例如 "claude-code" → "claude_code"。
   *
   * @param scope URL scope 参数
   * @return agent path 段
   */
  public static String scopeToAgentUrl(String scope) {
    if (scope == null || scope.isEmpty()) {
      return scope;
    }
    if ("all".equals(scope)) {
      return "claude_code";
    }
    String dbValue = scope;
    for (Map.Entry<String, String> entry : DB_TO_SCOPE.entrySet()) {
      if (entry.getValue().equals(scope)) {
        dbValue = entry.getKey();
        break;
      }
    }
    return dbValue;
  }

  /**
   * 将严重度字符串映射为 badge 变体 CSS 类名。
   *
   * <p>"high"/"error" → "danger"，"medium"/"warning" → "warning"，其他 → "info"。
   *
   * @param severity 严重度标签
   * @return CSS 变体类名
   */
  public static String severityVariant(String severity) {
    if (severity == null || severity.isEmpty()) {
      return "info";
    }
    String lower = severity.toLowerCase();
    if (lower.contains("high") || lower.contains("error")) {
      return "danger";
    }
    if (lower.contains("medium") || lower.contains("warning")) {
      return "warning";
    }
    return "info";
  }

  /**
   * 对 Map 序列中指定属性求和。
   *
   * @param items Map 列表
   * @param attr 求和的属性键
   * @return 属性值总和
   */
  public static long sumAttribute(List<?> items, String attr) {
    if (items == null || items.isEmpty()) {
      return 0;
    }
    long total = 0;
    for (Object item : items) {
      if (item instanceof Map<?, ?> map) {
        Object val = map.get(attr);
        if (val instanceof Number num) {
          total += num.longValue();
        }
      }
    }
    return total;
  }

  /**
   * 将任意对象序列化为 JSON 字符串。
   *
   * <p>轻量级实现，支持 Map、List、String、Number、Boolean、null。 不依赖 Jackson，避免模板基础设施引入重量级序列化库。
   */
  public static final class SimpleJson {

    private SimpleJson() {}

    /**
     * 将对象序列化为 JSON 字符串并进行 HTML 转义。
     *
     * @param value 要序列化的对象
     * @return HTML 转义后的 JSON 字符串
     */
    public static String toJson(Object value) {
      StringWriter writer = new StringWriter();
      writeValue(writer, value);
      return SafeHtml.escaped(writer.toString()).value();
    }

    private static void writeValue(StringWriter w, Object value) {
      if (value == null) {
        w.write("null");
      } else if (value instanceof String s) {
        writeString(w, s);
      } else if (value instanceof Number) {
        w.write(value.toString());
      } else if (value instanceof Boolean b) {
        w.write(b.toString());
      } else if (value instanceof Map<?, ?> map) {
        writeMap(w, map);
      } else if (value instanceof List<?> list) {
        writeList(w, list);
      } else if (value.getClass().isArray()) {
        writeList(w, List.of((Object[]) value));
      } else {
        writeString(w, value.toString());
      }
    }

    private static void writeString(StringWriter w, String s) {
      w.write('"');
      for (int i = 0; i < s.length(); i++) {
        char c = s.charAt(i);
        switch (c) {
          case '"' -> w.write("\\\"");
          case '\\' -> w.write("\\\\");
          case '\n' -> w.write("\\n");
          case '\r' -> w.write("\\r");
          case '\t' -> w.write("\\t");
          case '\b' -> w.write("\\b");
          case '\f' -> w.write("\\f");
          default -> {
            if (c < 0x20) {
              w.write(String.format("\\u%04x", (int) c));
            } else {
              w.write(c);
            }
          }
        }
      }
      w.write('"');
    }

    private static void writeMap(StringWriter w, Map<?, ?> map) {
      w.write('{');
      boolean first = true;
      for (Map.Entry<?, ?> entry : map.entrySet()) {
        if (!first) {
          w.write(',');
        }
        first = false;
        writeString(w, String.valueOf(entry.getKey()));
        w.write(':');
        writeValue(w, entry.getValue());
      }
      w.write('}');
    }

    private static void writeList(StringWriter w, List<?> list) {
      w.write('[');
      boolean first = true;
      for (Object item : list) {
        if (!first) {
          w.write(',');
        }
        first = false;
        writeValue(w, item);
      }
      w.write(']');
    }
  }
}
