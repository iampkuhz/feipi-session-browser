package com.feipi.session.browser.reuse.analyzer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.reuse.analyzer.model.AnalysisResult;
import com.feipi.session.browser.reuse.analyzer.model.InputManifest;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Analyzer 的命令行入口。 Gradle task 通过 JavaExec 调用此类执行分析。
 *
 * <p>用法：
 *
 * <pre>
 *   java -cp ... com.feipi.session.browser.reuse.analyzer.AnalyzerMain
 *       --mode full|incremental|selftest|baseline
 *       --manifest &lt;manifest.json&gt;
 *       --cache-dir &lt;path&gt;
 *       --bootstrap-state &lt;path&gt;
 *       --output &lt;report.json&gt;
 * </pre>
 */
public final class AnalyzerMain {

  private AnalyzerMain() {}

  /** 分析器命令行主入口方法。 */
  public static void main(String[] args) throws Exception {
    String mode = "full";
    String manifestPath = null;
    String cacheDir = null;
    String bootstrapState = null;
    String baselineFile = null;
    String outputPath = null;

    for (int i = 0; i < args.length; i++) {
      switch (args[i]) {
        case "--mode" -> mode = args[++i];
        case "--manifest" -> manifestPath = args[++i];
        case "--cache-dir" -> cacheDir = args[++i];
        case "--bootstrap-state" -> bootstrapState = args[++i];
        case "--baseline-file" -> baselineFile = args[++i];
        case "--output" -> outputPath = args[++i];
        default -> {
          System.err.println("未知参数：" + args[i]);
          System.exit(1);
        }
      }
    }

    ObjectMapper mapper = new ObjectMapper();
    Path cacheDirectory =
        cacheDir != null ? Path.of(cacheDir) : Path.of(".gradle", "feipi-reuse-analysis");

    ReuseAnalyzer analyzer = new ReuseAnalyzer(cacheDirectory);
    AnalysisResult result;

    switch (mode) {
      case "selftest" -> {
        result = analyzer.selfTest();
      }
      case "incremental" -> {
        if (manifestPath == null) {
          System.err.println("增量模式需要 --manifest 参数");
          System.exit(1);
        }
        InputManifest manifest = mapper.readValue(new File(manifestPath), InputManifest.class);
        Path bsPath = bootstrapState != null ? Path.of(bootstrapState) : null;
        result = analyzer.analyzeIncremental(manifest, bsPath);
      }
      case "baseline" -> {
        result = verifyBaseline(analyzer, manifestPath, baselineFile, mapper);
      }
      default -> {
        // 全量分析模式
        if (manifestPath == null) {
          System.err.println("全量模式需要 --manifest 参数");
          System.exit(1);
        }
        InputManifest manifest = mapper.readValue(new File(manifestPath), InputManifest.class);
        result = analyzer.analyzeFull(manifest);
      }
    }

    // 写入结果
    String json = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(result);
    if (outputPath != null) {
      Path outPath = Path.of(outputPath);
      Files.createDirectories(outPath.getParent());
      Files.writeString(outPath, json, StandardCharsets.UTF_8);
    }
    System.out.println(json);

    // 按 status 设置退出码
    if ("FAIL".equals(result.status())) {
      System.exit(1);
    }
  }

  private static AnalysisResult verifyBaseline(
      ReuseAnalyzer analyzer, String manifestPath, String baselineFilePath, ObjectMapper mapper)
      throws Exception {
    if (manifestPath == null) {
      return AnalysisResult.bootstrapRequired("baseline 验证需要 --manifest 参数");
    }
    InputManifest manifest = mapper.readValue(new File(manifestPath), InputManifest.class);
    Path baselinePath = baselineFilePath != null ? Path.of(baselineFilePath) : null;
    return analyzer.verifyBaseline(manifest, baselinePath);
  }
}
