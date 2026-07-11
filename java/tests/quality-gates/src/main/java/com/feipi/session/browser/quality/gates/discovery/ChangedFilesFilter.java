package com.feipi.session.browser.quality.gates.discovery;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * 基于环境变量的变更文件过滤器。
 *
 * <p>如果环境变量 {@code QUALITY_CHANGED_FILES} 存在且为 JSON 列表， 则只保留命中的主源集 Java 文件；否则返回原列表。
 */
public final class ChangedFilesFilter {

  private ChangedFilesFilter() {}

  /**
   * 根据环境变量过滤文件列表。
   *
   * @param files 已发现的 Java 文件列表。
   * @param changedJson 环境变量值；null 或空时返回原列表。
   * @param repoRoot 仓库根目录，用于计算相对路径。
   * @return 过滤后的文件列表。
   */
  public static List<Path> filter(List<Path> files, String changedJson, Path repoRoot) {
    if (changedJson == null || changedJson.isBlank()) {
      return files;
    }
    Set<String> changed = parseChangedFiles(changedJson, repoRoot);
    if (changed.isEmpty()) {
      return files;
    }
    var result = new ArrayList<Path>();
    for (var file : files) {
      var relative = toRelativePosix(file, repoRoot);
      if (changed.contains(relative)) {
        result.add(file);
      }
    }
    return result;
  }

  /**
   * 解析 QUALITY_CHANGED_FILES JSON 列表。
   *
   * <p>简单 JSON 数组解析，避免引入额外依赖。
   *
   * @param json JSON 字符串。
   * @param repoRoot 仓库根目录。
   * @return 解析后的路径集合；解析失败返回空集合。
   */
  static Set<String> parseChangedFiles(String json, Path repoRoot) {
    var result = new java.util.LinkedHashSet<String>();
    var trimmed = json.trim();
    if (!trimmed.startsWith("[") || !trimmed.endsWith("]")) {
      return result;
    }
    var inner = trimmed.substring(1, trimmed.length() - 1).trim();
    if (inner.isEmpty()) {
      return result;
    }
    for (var token : inner.split(",")) {
      var unquoted = token.trim();
      if (unquoted.startsWith("\"") && unquoted.endsWith("\"") && unquoted.length() >= 2) {
        unquoted = unquoted.substring(1, unquoted.length() - 1);
      }
      if (unquoted.endsWith(".java") && FileDiscovery.isMainJavaSource(Path.of(unquoted))) {
        result.add(unquoted);
      }
    }
    return result;
  }

  private static String toRelativePosix(Path file, Path repoRoot) {
    try {
      var relative =
          repoRoot.toAbsolutePath().normalize().relativize(file.toAbsolutePath().normalize());
      return relative.toString().replace('\\', '/');
    } catch (IllegalArgumentException e) {
      return file.toString().replace('\\', '/');
    }
  }

  /**
   * 从文件读取 changed files JSON。
   *
   * @param filesFrom 文件路径。
   * @return JSON 字符串。
   */
  public static String readFilesFrom(Path filesFrom) {
    try {
      return Files.readString(filesFrom, StandardCharsets.UTF_8).trim();
    } catch (Exception e) {
      return "";
    }
  }
}
