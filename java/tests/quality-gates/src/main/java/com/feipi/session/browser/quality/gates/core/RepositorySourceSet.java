package com.feipi.session.browser.quality.gates.core;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

/**
 * 一次质量门执行共享的仓库文本源码集合。
 *
 * <p>该集合只读取 CLI 明确传入根目录下的受支持文本源码；它不解释 Java AST，也不扫描 Git。
 *
 * @param sources 已按仓库相对路径排序的文本源码。
 */
public record RepositorySourceSet(List<SourceText> sources) {

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

  /** 对源码列表做防御性复制，保证规则之间不能相互修改候选。 */
  public RepositorySourceSet {
    sources = List.copyOf(sources);
  }

  /**
   * 从显式输入路径发现并读取受规则支持的文本源码。
   *
   * @param repoRoot 仓库根目录。
   * @param inputs 文件或目录输入。
   * @param supportedPath 判断仓库相对路径是否属于已选择规则。
   * @return 稳定排序且不可变的源码集合。
   * @throws IOException 路径遍历或源码读取失败。
   */
  public static RepositorySourceSet discover(
      Path repoRoot, List<Path> inputs, Predicate<String> supportedPath) throws IOException {
    var normalizedRoot = repoRoot.toAbsolutePath().normalize();
    var candidates = new LinkedHashSet<Path>();
    for (var input : inputs) {
      var path = input.isAbsolute() ? input : normalizedRoot.resolve(input);
      path = path.toAbsolutePath().normalize();
      if (Files.isRegularFile(path)) {
        addIfSupported(normalizedRoot, path, supportedPath, candidates);
      } else if (Files.isDirectory(path)) {
        try (var stream = Files.walk(path)) {
          stream
              .filter(Files::isRegularFile)
              // build/generated/vendor 等排除项只属于 JVM 源码扫描；固定 Web 资源根必须完整遍历。
              .filter(
                  candidate ->
                      !isJvmSource(candidate) || !hasExcludedPart(normalizedRoot, candidate))
              .forEach(
                  candidate ->
                      addIfSupported(normalizedRoot, candidate, supportedPath, candidates));
        }
      }
    }
    var sources = new ArrayList<SourceText>();
    for (var path : candidates) {
      sources.add(
          new SourceText(
              path,
              relativePath(normalizedRoot, path),
              new String(Files.readAllBytes(path), StandardCharsets.UTF_8)));
    }
    sources.sort(Comparator.comparing(SourceText::relativePath));
    return new RepositorySourceSet(sources);
  }

  private static void addIfSupported(
      Path repoRoot, Path path, Predicate<String> supportedPath, LinkedHashSet<Path> candidates) {
    if (supportedPath.test(relativePath(repoRoot, path))) {
      candidates.add(path);
    }
  }

  private static boolean hasExcludedPart(Path repoRoot, Path path) {
    Path relative;
    try {
      relative = repoRoot.relativize(path.toAbsolutePath().normalize());
    } catch (IllegalArgumentException ignored) {
      relative = path;
    }
    for (var part : relative) {
      if (EXCLUDED_PARTS.contains(part.toString())) {
        return true;
      }
    }
    return false;
  }

  private static boolean isJvmSource(Path path) {
    var fileName = path.getFileName().toString();
    return fileName.endsWith(".java") || fileName.endsWith(".kt") || fileName.endsWith(".kts");
  }

  private static String relativePath(Path repoRoot, Path path) {
    return JavaSourceSet.normalize(repoRoot.relativize(path.toAbsolutePath().normalize()));
  }

  /**
   * 单个仓库文本源码。
   *
   * @param path 绝对路径。
   * @param relativePath 仓库相对 POSIX 路径。
   * @param text UTF-8 源码内容。
   */
  public record SourceText(Path path, String relativePath, String text) {}
}
