package com.feipi.session.browser.artifact.normalized;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * 安全的 artifact 文件名生成器。
 *
 * <p>对 artifact key（通常是 session key）进行清洗，确保生成的文件名安全、可移植且不会导致路径遍历攻击。
 *
 * <p>处理规则：
 *
 * <ul>
 *   <li>路径遍历：拒绝 {@code ..}、绝对路径、包含路径分隔符的输入。
 *   <li>Windows 保留名：{@code CON}、{@code PRN}、{@code AUX}、{@code NUL}、{@code COM1-8}、{@code LPT1-8}。
 *   <li>非法字符：替换为下划线。
 *   <li>长度限制：超过 {@value #MAX_NAME_LENGTH} 字符时截断并附加 hash 后缀。
 *   <li>空或全非法字符：使用内容 hash 作为 fallback。
 * </ul>
 */
public final class SafeArtifactName {

  /** 文件名最大长度（不含扩展名）。 */
  public static final int MAX_NAME_LENGTH = 200;

  /** hash 后缀长度（用于截断后的唯一性保证）。 */
  private static final int HASH_SUFFIX_LENGTH = 8;

  /** Windows 保留文件名集合（大写形式）。 */
  private static final Set<String> WINDOWS_RESERVED =
      Set.of(
          "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7",
          "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9");

  /** 匹配 Windows 平台非法文件名字符。 */
  private static final Pattern ILLEGAL_CHARS = Pattern.compile("[\\\\/:*?\"<>|\\x00-\\x1f]");

  /** 禁止实例化。 */
  private SafeArtifactName() {}

  /**
   * 将原始 artifact key 清洗为安全的文件名基础部分。
   *
   * <p>清洗后的名称可直接用作文件名的 stem，不含扩展名。
   *
   * @param rawKey 原始 artifact key，不得为 null 或空
   * @return 安全文件名基础部分
   * @throws IllegalArgumentException 当 key 包含路径遍历尝试或为绝对路径时
   */
  public static String sanitize(String rawKey) {
    if (rawKey == null || rawKey.isBlank()) {
      throw new IllegalArgumentException("artifact key 不得为 null 或空");
    }

    // 路径遍历防护：拒绝 .. 组件
    if (rawKey.contains("..")) {
      throw new IllegalArgumentException("artifact key 包含路径遍历: " + rawKey);
    }

    // 路径遍历防护：拒绝绝对路径（Unix 风格 / 或 Windows 风格 C:\ 等）
    // 必须在路径分隔符检查之前，因为绝对路径必然包含分隔符
    if (rawKey.startsWith("/")
        || (rawKey.length() >= 2
            && Character.isLetter(rawKey.charAt(0))
            && rawKey.charAt(1) == ':')) {
      throw new IllegalArgumentException("artifact key 不得为绝对路径: " + rawKey);
    }

    // 路径遍历防护：拒绝路径分隔符
    if (rawKey.contains("/") || rawKey.contains("\\")) {
      throw new IllegalArgumentException("artifact key 包含路径分隔符: " + rawKey);
    }

    String sanitized = rawKey.strip();

    // 替换 Windows 非法字符
    sanitized = ILLEGAL_CHARS.matcher(sanitized).replaceAll("_");

    // 去除首尾控制字符和点号（防止隐藏文件）
    while (!sanitized.isEmpty()
        && (sanitized.charAt(0) == '.' || Character.isISOControl(sanitized.charAt(0)))) {
      sanitized = sanitized.substring(1);
    }
    while (!sanitized.isEmpty()
        && (sanitized.charAt(sanitized.length() - 1) == '.'
            || Character.isISOControl(sanitized.charAt(sanitized.length() - 1)))) {
      sanitized = sanitized.substring(0, sanitized.length() - 1);
    }

    // Windows 保留名检查（带或不带扩展名均拒绝）
    String baseName =
        sanitized.contains(".") ? sanitized.substring(0, sanitized.indexOf('.')) : sanitized;
    if (WINDOWS_RESERVED.contains(baseName.toUpperCase())) {
      sanitized = "_" + sanitized;
    }

    // 空值回退
    if (sanitized.isEmpty()) {
      sanitized = "artifact-" + shortHash(rawKey);
    }

    // 长度限制
    if (sanitized.length() > MAX_NAME_LENGTH) {
      sanitized = appendHashSuffix(sanitized, rawKey);
    }

    return sanitized;
  }

  /**
   * 生成带确定性消歧后缀的安全文件名基础部分。
   *
   * <p>当 key 清洗后可能与其它输入在大小写、Unicode normalization 或非法字符替换后落到同一路径时，附加 raw key 的短 hash。这样同一 key
   * 仍保持确定性，不同但路径等价的 key 不会互相覆盖。
   *
   * @param rawKey 原始 artifact key，不得为 null 或空
   * @return 可用于 artifact 文件名的安全基础部分
   */
  static String collisionResistantStem(String rawKey) {
    String sanitized = sanitize(rawKey);
    if (!needsDisambiguation(rawKey, sanitized)) {
      return sanitized;
    }
    return appendHashSuffix(sanitized, rawKey);
  }

  private static String appendHashSuffix(String sanitized, String rawKey) {
    int prefixLength = MAX_NAME_LENGTH - HASH_SUFFIX_LENGTH - 1;
    String prefix =
        sanitized.length() > prefixLength ? sanitized.substring(0, prefixLength) : sanitized;
    return prefix + "-" + shortHash(rawKey);
  }

  /**
   * 验证 output root 本身可安全写入。
   *
   * @param outputRoot 输出根目录
   * @throws IllegalArgumentException 当 root 不存在、不是目录或本身是 symlink 时
   */
  static void validateOutputRoot(Path outputRoot) {
    if (Files.isSymbolicLink(outputRoot)) {
      throw new IllegalArgumentException("output root 不得为 symlink: " + outputRoot);
    }
    if (!Files.isDirectory(outputRoot, LinkOption.NOFOLLOW_LINKS)) {
      throw new IllegalArgumentException("output root 必须是已存在目录: " + outputRoot);
    }
  }

  /**
   * 验证解析后的目标路径是否仍在 output root 内。
   *
   * @param outputRoot 输出根目录
   * @param target 目标文件路径
   * @throws IllegalArgumentException 当目标路径逃逸出 output root 时
   */
  public static void validateWithinRoot(Path outputRoot, Path target) {
    Path normalizedRoot = outputRoot.toAbsolutePath().normalize();
    Path normalizedTarget = target.toAbsolutePath().normalize();

    if (!normalizedTarget.startsWith(normalizedRoot)) {
      throw new IllegalArgumentException(
          "目标路径逃逸出 output root: " + target + " 不在 " + outputRoot + " 内");
    }

    // symlink 逃逸检查
    try {
      if (Files.exists(target)) {
        Path realTarget = target.toRealPath();
        Path realRoot = outputRoot.toRealPath();
        if (!realTarget.startsWith(realRoot)) {
          throw new IllegalArgumentException(
              "symlink 逃逸: " + target + " 解析到 " + realTarget + "，不在 " + realRoot + " 内");
        }
      } else if (target.getParent() != null && Files.exists(target.getParent())) {
        Path realParent = target.getParent().toRealPath();
        Path realRoot = outputRoot.toRealPath();
        if (!realParent.startsWith(realRoot)) {
          throw new IllegalArgumentException(
              "symlink 逃逸: 父目录 "
                  + target.getParent()
                  + " 解析到 "
                  + realParent
                  + "，不在 "
                  + realRoot
                  + " 内");
        }
      }
    } catch (IOException e) {
      throw new UncheckedIOException("路径验证失败", e);
    }
  }

  private static boolean needsDisambiguation(String rawKey, String sanitized) {
    return !sanitized.equals(rawKey)
        || !rawKey.equals(rawKey.toLowerCase(Locale.ROOT))
        || !Normalizer.isNormalized(rawKey, Normalizer.Form.NFC);
  }

  /**
   * 计算字符串的短 hash（8 个十六进制字符）。
   *
   * @param input 输入字符串
   * @return 8 字符十六进制 hash
   */
  private static String shortHash(String input) {
    try {
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(hash).substring(0, HASH_SUFFIX_LENGTH);
    } catch (NoSuchAlgorithmException e) {
      // SHA-256 在所有 Java 实现中都可用，此处不会触发
      return Integer.toHexString(input.hashCode());
    }
  }
}
