package com.feipi.session.browser.source.spi;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/**
 * 源适配器家族的共享操作。
 *
 * <p>封装三种源适配器（Claude Code、Codex、Qoder）及其发现类中完全相同的路径、 文件和哈希方法，消除跨模块的代码重复。
 *
 * <p>该类是不可变的，线程安全。
 */
public final class SourcePathOps {

  /** SHA-256 哈希算法名称。 */
  private static final String HASH_ALGORITHM = "SHA-256";

  /** 文件读取缓冲区大小（字节）。 */
  private static final int READ_BUFFER_SIZE = 8192;

  private SourcePathOps() {
    // 静态工具类，禁止实例化
  }

  /**
   * 将绝对路径转为相对于根目录的路径。
   *
   * <p>对两个路径先取绝对路径再规范化后执行 relativize。 当两个路径不在同一根下导致 {@link IllegalArgumentException} 时， 回退返回原始
   * {@code filePath}。
   *
   * @param rootPath 根目录
   * @param filePath 文件路径
   * @return 相对路径，或无法相对化时的原始文件路径
   */
  public static Path toRelative(Path rootPath, Path filePath) {
    try {
      return rootPath
          .toAbsolutePath()
          .normalize()
          .relativize(filePath.toAbsolutePath().normalize());
    } catch (IllegalArgumentException e) {
      return filePath;
    }
  }

  /**
   * 去除字符串末尾的指定后缀内容，若不存在则返回原文本。
   *
   * @param text 原始文本
   * @param suffix 待去除的后缀
   * @return 去除后缀后的文本，或原文本
   */
  public static String stripSuffix(String text, String suffix) {
    if (text.endsWith(suffix)) {
      return text.substring(0, text.length() - suffix.length());
    }
    return text;
  }

  /**
   * 判断路径是否为隐藏文件/目录（名称以 {@code .} 开头）。
   *
   * @param path 待检查路径
   * @return 隐藏时返回 {@code true}
   */
  public static boolean isHidden(Path path) {
    String name = path.getFileName().toString();
    return name.startsWith(".");
  }

  /**
   * 计算文件的 SHA-256 内容哈希。
   *
   * @param filePath 文件路径
   * @return 十六进制哈希字符串
   * @throws IOException 当文件读取失败时
   */
  public static String computeSha256(Path filePath) throws IOException {
    try {
      MessageDigest digest = MessageDigest.getInstance(HASH_ALGORITHM);
      byte[] buffer = new byte[READ_BUFFER_SIZE];
      try (var input = Files.newInputStream(filePath)) {
        int bytesRead;
        while ((bytesRead = input.read(buffer)) != -1) {
          digest.update(buffer, 0, bytesRead);
        }
      }
      return HexFormat.of().formatHex(digest.digest());
    } catch (NoSuchAlgorithmException e) {
      // SHA-256 是 JDK 必需算法，不应发生
      throw new IllegalStateException("SHA-256 算法不可用", e);
    }
  }
}
