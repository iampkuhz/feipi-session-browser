package com.feipi.session.browser.quality.gates.discovery;

import java.io.IOException;
import java.nio.file.FileVisitOption;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;

/**
 * Java 源文件发现器。
 *
 * <p>只保留位于 {@code src/main/java} 源集的 Java 文件，排除构建产物和第三方目录。
 */
public final class FileDiscovery {

  /** 排除的路径片段。 */
  private static final Set<String> EXCLUDED_PARTS =
      Set.of(
          "build",
          ".gradle",
          "generated",
          "gen",
          "third_party",
          "vendor",
          "node_modules",
          "__pycache__",
          "tmp");

  private FileDiscovery() {}

  /**
   * 从输入路径列表中发现所有待检查的 Java 文件。
   *
   * @param inputPaths 命令行传入的路径列表。
   * @return 排序后的文件列表。
   * @throws IOException 文件系统访问失败时抛出。
   */
  public static List<Path> discover(List<Path> inputPaths) throws IOException {
    Set<Path> result = new LinkedHashSet<>();
    for (var path : inputPaths) {
      if (Files.isRegularFile(path) && path.getFileName().toString().endsWith(".java")) {
        result.add(path);
      } else if (Files.isDirectory(path)) {
        try (Stream<Path> stream = Files.walk(path, FileVisitOption.FOLLOW_LINKS)) {
          stream.filter(FileDiscovery::isCandidate).forEach(result::add);
        }
      }
    }
    var sorted = new ArrayList<>(result);
    sorted.sort(Comparator.comparing(Path::toString));
    return sorted;
  }

  /**
   * 判断路径是否为候选文件：位于 {@code src/main/java}、不在排除目录中。
   *
   * @param path 文件路径。
   * @return 是否满足条件。
   */
  public static boolean isCandidate(Path path) {
    if (!path.getFileName().toString().endsWith(".java")) {
      return false;
    }
    if (!isMainJavaSource(path)) {
      return false;
    }
    for (var part : getParts(path)) {
      if (EXCLUDED_PARTS.contains(part)) {
        return false;
      }
    }
    return true;
  }

  /**
   * 判断路径是否位于 Gradle/Maven {@code src/main/java} 源集。
   *
   * @param path 文件路径。
   * @return 是否位于主源集。
   */
  public static boolean isMainJavaSource(Path path) {
    var parts = getParts(path);
    for (int i = 0; i + 2 < parts.length; i++) {
      if (parts[i].equals("src") && parts[i + 1].equals("main") && parts[i + 2].equals("java")) {
        return true;
      }
    }
    return false;
  }

  /**
   * 获取路径的所有片段。
   *
   * @param path 文件路径。
   * @return 路径片段数组。
   */
  private static String[] getParts(Path path) {
    var parts = new ArrayList<String>();
    for (var name : path) {
      parts.add(name.toString());
    }
    return parts.toArray(new String[0]);
  }
}
