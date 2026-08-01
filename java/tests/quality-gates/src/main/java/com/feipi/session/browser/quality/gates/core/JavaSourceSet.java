package com.feipi.session.browser.quality.gates.core;

import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.DocTrees;
import com.sun.source.util.JavacTask;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaFileObject;
import javax.tools.ToolProvider;

/**
 * 一次 compiler parse 的 Java 源码集合。
 *
 * <p>所有规则共享同一批 {@link CompilationUnitTree}、{@link DocTrees} 和源码位置；规则不得自行扫描 Git 或再次解析源码。
 *
 * @param sources 已按仓库相对路径排序的源码。
 * @param docTrees JDK compiler 文档树入口；纯 Kotlin 候选时为空。
 */
public record JavaSourceSet(List<ParsedSource> sources, DocTrees docTrees) {

  /**
   * 解析明确传入的候选文件。
   *
   * @param repoRoot 仓库根目录。
   * @param candidates 候选 Java 文件。
   * @return 单次 parse 的源码集合。
   * @throws IOException 文件读取失败或源码存在 parse error。
   */
  public static JavaSourceSet parse(Path repoRoot, List<Path> candidates) throws IOException {
    var compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null) {
      throw new IOException("JDK compiler is unavailable");
    }
    var diagnostics = new DiagnosticCollector<JavaFileObject>();
    try (var files = compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
      var task =
          (JavacTask)
              compiler.getTask(
                  null,
                  files,
                  diagnostics,
                  List.of("-proc:none", "-Xlint:none"),
                  null,
                  files.getJavaFileObjectsFromPaths(candidates));
      var trees = DocTrees.instance(task);
      var parsed = new ArrayList<ParsedSource>();
      for (var unit : task.parse()) {
        var path = Path.of(unit.getSourceFile().toUri()).toAbsolutePath().normalize();
        var relative = normalize(repoRoot.toAbsolutePath().normalize().relativize(path));
        parsed.add(
            new ParsedSource(
                path,
                relative,
                java.nio.file.Files.readString(path, StandardCharsets.UTF_8),
                unit));
      }
      var errors =
          diagnostics.getDiagnostics().stream()
              .filter(item -> item.getKind() == Diagnostic.Kind.ERROR)
              .map(
                  item ->
                      item.getSource() + ":" + item.getLineNumber() + ": " + item.getMessage(null))
              .toList();
      if (!errors.isEmpty()) {
        throw new IOException("Java source parse failed: " + String.join("; ", errors));
      }
      parsed.sort(Comparator.comparing(ParsedSource::relativePath));
      return new JavaSourceSet(List.copyOf(parsed), trees);
    }
  }

  /** 将路径稳定规范化为 POSIX 仓库相对形式。 */
  public static String normalize(Path path) {
    return path.normalize().toString().replace('\\', '/');
  }

  /**
   * 单个 compiler compilation unit 及其原始源码。
   *
   * @param path 绝对路径。
   * @param relativePath 仓库相对 POSIX 路径。
   * @param text UTF-8 源码。
   * @param unit compiler 生成的源码抽象语法树。
   */
  public record ParsedSource(
      Path path, String relativePath, String text, CompilationUnitTree unit) {}
}
