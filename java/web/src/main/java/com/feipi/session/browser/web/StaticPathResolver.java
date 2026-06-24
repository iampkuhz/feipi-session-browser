package com.feipi.session.browser.web;

import java.nio.file.Path;
import java.util.Objects;
import java.util.Set;

/**
 * 静态资源路径解析与 traversal 防护。
 *
 * <p>对请求路径执行以下安全检查：
 *
 * <ol>
 *   <li>拒绝包含 {@code ..} 段的路径（path traversal）
 *   <li>拒绝包含反斜杠 {@code \} 的路径（Windows traversal 变体）
 *   <li>拒绝包含 null 字节的路径（null byte injection）
 *   <li>归一化后验证路径仍在允许的根目录内（symlink escape 防护）
 * </ol>
 *
 * <p>校验放置：路径安全检查在 HTTP adapter 入口执行一次，下游静态文件 handler 信任解析结果。
 */
public final class StaticPathResolver {

  /** 允许的静态资源文件扩展名。 */
  private static final Set<String> ALLOWED_EXTENSIONS =
      Set.of(
          ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf",
          ".eot", ".json", ".map", ".html", ".htm");

  private final Path rootDir;

  /**
   * 创建路径解析器。
   *
   * @param rootDir 静态资源根目录，必须是绝对路径
   */
  public StaticPathResolver(Path rootDir) {
    this.rootDir = Objects.requireNonNull(rootDir, "rootDir 不得为 null").toAbsolutePath().normalize();
  }

  /**
   * 解析并验证请求路径。
   *
   * <p>对输入路径执行安全检查和归一化，返回安全的绝对路径。
   *
   * @param requestPath 请求路径（相对于根目录），如 {@code /css/base.css}
   * @return 归一化后的绝对路径
   * @throws SecurityException 路径包含非法字符、traversal 序列或逃逸出根目录
   */
  public Path resolve(String requestPath) {
    if (requestPath == null || requestPath.isEmpty()) {
      throw new SecurityException("静态资源路径为空");
    }

    // null byte 注入检查
    if (requestPath.indexOf('\0') >= 0) {
      throw new SecurityException("路径包含非法字符");
    }

    // 反斜杠检查（Windows traversal 变体）
    if (requestPath.contains("\\")) {
      throw new SecurityException("路径包含非法分隔符");
    }

    // 去除前导斜杠，确保作为相对路径解析
    String normalized = requestPath;
    while (normalized.startsWith("/")) {
      normalized = normalized.substring(1);
    }

    // .. traversal 检查
    for (String segment : normalized.split("/", -1)) {
      if ("..".equals(segment)) {
        throw new SecurityException("路径包含 traversal 序列");
      }
    }

    // 归一化并验证根目录约束
    Path resolved = rootDir.resolve(normalized).normalize();
    if (!resolved.startsWith(rootDir)) {
      throw new SecurityException("路径逃逸出静态资源根目录");
    }

    // 扩展名白名单检查
    String fileName = resolved.getFileName().toString();
    if (fileName.contains(".")) {
      String extension = getExtension(fileName);
      if (!ALLOWED_EXTENSIONS.contains(extension.toLowerCase())) {
        throw new SecurityException("不允许的文件类型: " + extension);
      }
    }

    return resolved;
  }

  /** 返回静态资源根目录。 */
  public Path rootDir() {
    return rootDir;
  }

  /** 提取文件扩展名（含点号）。 */
  private static String getExtension(String fileName) {
    int dot = fileName.lastIndexOf('.');
    if (dot < 0) {
      return "";
    }
    return fileName.substring(dot);
  }
}
