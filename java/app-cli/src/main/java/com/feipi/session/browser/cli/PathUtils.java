package com.feipi.session.browser.cli;

/**
 * 路径工具类。
 *
 * <p>提供跨命令共享的路径处理方法。所有方法为纯函数，不访问文件系统。
 */
public final class PathUtils {

  private PathUtils() {}

  /**
   * 展开路径中的 {@code ~} 为用户主目录。
   *
   * <p>{@code ~/foo} 展开为 {@code $HOME/foo}，{@code ~} 展开为 {@code $HOME}。
   *
   * @param path 原始路径
   * @return 展开后的路径
   */
  public static String expandTilde(String path) {
    if (path.startsWith("~/")) {
      return System.getProperty("user.home") + path.substring(1);
    }
    if (path.equals("~")) {
      return System.getProperty("user.home");
    }
    return path;
  }
}
