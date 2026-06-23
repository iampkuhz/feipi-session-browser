package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 会话源文件重命名/移动检测器。
 *
 * <p>当一个已索引会话的存储文件路径不存在时，尝试在同一源的其他项目目录中查找相同的 session_id。 如果找到，则认为会话被移动/重命名，返回新的文件路径。
 *
 * <p>检测策略：
 *
 * <ol>
 *   <li>从 session key 中提取 session_id 部分。
 *   <li>遍历源根目录下的所有项目子目录。
 *   <li>查找文件名包含 session_id 的源文件。
 *   <li>找到第一个匹配且存在的文件即返回。
 * </ol>
 *
 * <p>不在网络文件系统假设 WAL/atomic move。
 */
final class RenameDetector {

  private static final Logger log = LoggerFactory.getLogger(RenameDetector.class);

  /** 防止实例化。 */
  private RenameDetector() {}

  /**
   * 尝试检测会话是否已移动到新位置。
   *
   * <p>从 {@code storedSessionKey} 中提取 session_id，然后在 {@code rootPath} 下搜索包含该 session_id 的源文件。
   *
   * @param adapter 源适配器
   * @param rootPath 源根目录
   * @param storedSessionKey 已索引的会话主键（格式：{@code agent:session_id}）
   * @return 新文件路径和 mtime，未找到时返回 {@link Optional#empty()}
   */
  static Optional<RenameResult> detectRename(
      SourceAdapter adapter, Path rootPath, String storedSessionKey) {
    Objects.requireNonNull(adapter, "adapter 不得为 null");
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");
    Objects.requireNonNull(storedSessionKey, "storedSessionKey 不得为 null");

    // 从 session key 提取 session_id
    String sessionId = extractSessionId(storedSessionKey);
    if (sessionId.isEmpty()) {
      return Optional.empty();
    }

    // 检查根目录是否可访问
    if (!Files.isDirectory(rootPath)) {
      return Optional.empty();
    }

    // 在根目录下搜索包含 session_id 的文件
    try (var stream = Files.walk(rootPath, 10)) {
      return stream
          .filter(Files::isRegularFile)
          .filter(p -> containsSessionId(p.getFileName().toString(), sessionId))
          .findFirst()
          .map(
              p -> {
                double mtime = getFileMtime(p);
                return new RenameResult(p.toString(), mtime);
              });
    } catch (IOException e) {
      log.debug("重命名检测遍历失败: {} - {}", rootPath, e.getMessage());
      return Optional.empty();
    }
  }

  /**
   * 检查源根目录是否可访问。
   *
   * <p>使用 {@link SourceAdapter#checkRoot} 检查根目录的安全性和可用性。 如果根目录不可访问（如权限不足、网络断开），返回 false。
   *
   * @param adapter 源适配器
   * @param rootPath 源根目录
   * @return 根目录可访问且安全时返回 true
   */
  static boolean isRootAccessible(SourceAdapter adapter, Path rootPath) {
    Objects.requireNonNull(adapter, "adapter 不得为 null");
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    if (!Files.exists(rootPath)) {
      return false;
    }

    SourceRoot root = adapter.checkRoot(rootPath);
    return root.isSafe();
  }

  /**
   * 从 session key 中提取 session_id 部分。
   *
   * <p>session key 格式为 {@code agent:session_id}，返回冒号后的部分。
   *
   * @param sessionKey 会话主键
   * @return session_id 部分，无冒号时返回原始值
   */
  static String extractSessionId(String sessionKey) {
    int colonIndex = sessionKey.indexOf(':');
    if (colonIndex >= 0 && colonIndex < sessionKey.length() - 1) {
      return sessionKey.substring(colonIndex + 1);
    }
    return sessionKey;
  }

  /**
   * 检查文件名是否包含指定的 session_id。
   *
   * <p>去除文件扩展名后检查文件名主体是否等于或包含 session_id。
   *
   * @param fileName 文件名
   * @param sessionId session_id
   * @return 匹配时返回 true
   */
  private static boolean containsSessionId(String fileName, String sessionId) {
    // 去掉扩展名
    int dotIndex = fileName.lastIndexOf('.');
    String stem = dotIndex > 0 ? fileName.substring(0, dotIndex) : fileName;
    // 完全匹配或包含 session_id
    return stem.equals(sessionId) || stem.contains(sessionId);
  }

  /**
   * 获取文件的修改时间（epoch 秒）。
   *
   * @param path 文件路径
   * @return epoch 秒，获取失败时返回 0
   */
  private static double getFileMtime(Path path) {
    try {
      long mtimeMs = Files.getLastModifiedTime(path).toMillis();
      return mtimeMs / 1000.0;
    } catch (IOException e) {
      return 0.0;
    }
  }

  /**
   * 重命名检测结果。
   *
   * @param newFilePath 新文件路径
   * @param newFileMtime 新文件的修改时间（epoch 秒）
   */
  record RenameResult(String newFilePath, double newFileMtime) {

    /**
     * 紧凑构造器，验证非空。
     *
     * @throws NullPointerException 当 newFilePath 为 null 时
     */
    public RenameResult {
      Objects.requireNonNull(newFilePath, "newFilePath 不得为 null");
    }
  }
}
