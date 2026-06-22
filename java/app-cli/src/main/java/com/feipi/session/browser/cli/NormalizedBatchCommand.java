package com.feipi.session.browser.cli;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.Callable;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * 隐藏的批量归一化子命令。
 *
 * <p>从 stdin 读取 NDJSON（每行一个 JSON 对象，包含 {@code sourceId} 和 {@code rootPath}）， 对每个输入执行 发现 → 解析 → 归一化
 * → 写入制品流程， 并向 stdout 输出 NDJSON 结果（每行一个 JSON 对象，包含 {@code sessionKey}、{@code status}、{@code
 * artifactPath}、{@code error}）。
 *
 * <p>该命令通过 {@code hidden = true} 标记，不会出现在 help 输出中。
 */
@Command(
    name = "normalized-batch",
    description = "隐藏命令：批量归一化 session 并写入 artifact",
    hidden = true,
    mixinStandardHelpOptions = true)
final class NormalizedBatchCommand implements Callable<Integer> {

  @Option(
      names = {"--output-dir"},
      description = "artifact 输出目录",
      required = true)
  private Path outputDir;

  /**
   * 执行批量归一化流程。
   *
   * <p>从 stdin 逐行读取 NDJSON 输入，对每个输入项：
   *
   * <ol>
   *   <li>解析 {@code sourceId} 和 {@code rootPath}
   *   <li>通过 {@link SourceAdapterRegistry} 获取对应的 {@link SourceAdapter}
   *   <li>调用 {@link SourceAdapter#discover(Path)} 发现候选项
   *   <li>对每个候选项：读取 JSONL → 归一化 → 写入制品
   *   <li>向 stdout 输出结果行
   * </ol>
   *
   * @return 退出码，始终为 0
   * @throws Exception 当执行过程中发生不可恢复错误时
   */
  @Override
  public Integer call() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    Files.createDirectories(outputDir);

    try (BufferedReader reader =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        line = line.strip();
        if (line.isEmpty()) {
          continue;
        }
        processInputLine(line, mapper);
      }
    }

    System.out.flush();
    return 0;
  }

  /**
   * 处理单行 NDJSON 输入。
   *
   * @param line 输入行
   * @param mapper JSON 序列化器
   */
  private void processInputLine(String line, ObjectMapper mapper) {
    BatchInputRecord input;
    try {
      input = mapper.readValue(line, BatchInputRecord.class);
    } catch (Exception e) {
      writeOutput(
          mapper,
          new BatchOutputRecord("", "error", null, "Invalid input JSON: " + e.getMessage()));
      return;
    }

    if (input.sourceId() == null || input.rootPath() == null) {
      writeOutput(
          mapper,
          new BatchOutputRecord("", "error", null, "Missing sourceId or rootPath in input"));
      return;
    }

    try {
      SourceAdapter adapter = SourceAdapterRegistry.forSourceId(input.sourceId());
      Path rootPath = Path.of(input.rootPath());
      processRootInput(adapter, rootPath, input.rootPath(), mapper);
    } catch (IllegalArgumentException e) {
      writeOutput(mapper, new BatchOutputRecord("", "error", null, e.getMessage()));
    } catch (Exception e) {
      writeOutput(
          mapper, new BatchOutputRecord("", "error", null, "Processing error: " + e.getMessage()));
    }
  }

  /**
   * 对单个源根执行安全检查和候选项处理。
   *
   * @param adapter 源适配器
   * @param rootPath 根目录路径
   * @param rootPathStr 原始根路径字符串（用于错误消息）
   * @param mapper JSON 序列化器
   */
  private void processRootInput(
      SourceAdapter adapter, Path rootPath, String rootPathStr, ObjectMapper mapper) {
    SourceRoot root = adapter.checkRoot(rootPath);
    if (!root.isSafe()) {
      writeOutput(
          mapper, new BatchOutputRecord("", "error", null, "Unsafe root path: " + rootPathStr));
      return;
    }

    var candidates = adapter.discover(rootPath);
    for (Candidate candidate : candidates.orderedItems()) {
      processCandidate(candidate, adapter, mapper);
    }
  }

  /**
   * 处理单个候选项：读取 JSONL → 归一化 → 写入制品，并输出结果。
   *
   * @param candidate 待处理的候选项
   * @param adapter 源适配器
   * @param mapper JSON 序列化器
   */
  private void processCandidate(Candidate candidate, SourceAdapter adapter, ObjectMapper mapper) {
    String sessionKey = candidate.sessionKey();
    try {
      Path filePath = Path.of(candidate.fingerprint().path());
      JsonlReader jsonlReader = new JsonlReader();
      JsonlReaderResult readerResult = jsonlReader.read(filePath);
      List<JsonNode> events = readerResult.events();

      NormalizedSourceFile sourceFile =
          new NormalizedSourceFile(
              "transcript",
              filePath.toAbsolutePath().toString(),
              Optional.empty(),
              Optional.empty());

      String agent = adapter.sourceId().value();
      NormalizationEngine engine = new NormalizationEngine();
      var artifact =
          engine.normalize(agent, events, readerResult.diagnostics(), List.of(sourceFile));

      Map<String, String> fingerprints = buildFingerprints(filePath, candidate);

      NormalizedArtifactWriter writer = new NormalizedArtifactWriter();
      writer.write(outputDir, artifact, fingerprints);

      writeOutput(mapper, new BatchOutputRecord(sessionKey, "success", outputDir.toString(), null));
    } catch (Exception e) {
      writeOutput(mapper, new BatchOutputRecord(sessionKey, "error", null, e.getMessage()));
    }
  }

  /**
   * 从候选项指纹构建源文件指纹映射。
   *
   * @param filePath 源文件路径
   * @param candidate 候选项
   * @return 路径到内容哈希的映射
   */
  private static Map<String, String> buildFingerprints(Path filePath, Candidate candidate) {
    Optional<String> hash = candidate.fingerprint().contentHash();
    if (hash.isPresent()) {
      return Map.of(filePath.toAbsolutePath().toString(), hash.get());
    }
    return Map.of();
  }

  /**
   * 向 stdout 写入一行 NDJSON 结果。
   *
   * @param mapper JSON 序列化器
   * @param record 输出记录
   */
  private static void writeOutput(ObjectMapper mapper, BatchOutputRecord record) {
    try {
      System.out.println(mapper.writeValueAsString(record));
    } catch (Exception e) {
      System.err.println("Failed to serialize output: " + e.getMessage());
    }
  }
}
