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
 * <p><strong>用途</strong>：该命令用于“外部批处理入口”，供上游扫描管线（或脚本）调用；普通用户通常不会手工在终端直接使用它。它默认隐藏（{@code hidden =
 * true}），只在命令树中注册，不在 help 中展示。上游通常以管道方式触发：
 *
 * <pre>{@code
 * printf '{"sourceId":"CODEX","rootPath":"/path/to/codex/root"}\n' | session-browser normalized-batch --output-dir /tmp/artifacts
 * }</pre>
 *
 * <p><strong>输入</strong>：从 stdin 按行读取 NDJSON，每行要求至少包含 {@code sourceId} 与 {@code rootPath}。其中 {@code
 * sourceId} 决定采用 {@link SourceAdapterRegistry} 中哪个源适配器；{@code rootPath} 是该源的会话根目录（不是单个会话文件路径）。
 *
 * <p><strong>处理流程</strong>：逐行输入后，每个请求经过：
 *
 * <ol>
 *   <li>反序列化为 {@link BatchInputRecord}
 *   <li>通过 {@code sourceId} 解析适配器并校验根目录安全性（{@link SourceAdapter#checkRoot(Path)})
 *   <li>调用适配器发现会话候选项（{@link SourceAdapter#discover(Path)}）
 *   <li>对每个候选项读取其源文件（候选项 {@code fingerprint.locator} 指向的路径，通常是对应会话目录下的 {@code
 *       session.jsonl}），执行归一化，写入 normalized artifact
 * </ol>
 *
 * <p><strong>归一化的具体含义</strong>：将不同厂商 session 的原始事件流映射为统一 schema 的 {@link
 * com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact}。核心目标是把异构 JSONL
 * 变成可统一检索的会话模型，主要保留：
 *
 * <ul>
 *   <li>会话事件顺序与角色（user/assistant/tool）的标准化调用链（{@code calls}）
 *   <li>工具调用与结果的配对关系（{@code toolExecutions}）
 *   <li>解析诊断信息与 token 使用等元数据
 *   <li>源文件溯源信息（{@link NormalizedSourceFile}）
 * </ul>
 *
 * <p>经过此步，后续索引、统计和展示就能不再依赖各源的原始事件格式。
 *
 * <p><strong>输出</strong>：每处理一个候选会话，都会向 stdout 追加一行 JSON 对象（{@link BatchOutputRecord}），字段包含：
 *
 * <ul>
 *   <li>{@code sessionKey}：会话唯一标识
 *   <li>{@code status}：{@code success} 或 {@code error}
 *   <li>{@code artifactPath}：成功时为写入目录路径
 *   <li>{@code error}：失败时的错误信息
 * </ul>
 *
 * <p>即使单条输入失败，本命令整体仍会继续处理其余行，并最终返回码 {@code 0}。错误信息以每行 NDJSON 形式返回，避免污染 stderr，便于上游按行消费。
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
   *   <li>逐行解析输入行，得到待处理的 {@link BatchInputRecord}
   *   <li>通过 {@code sourceId} 选择源适配器并校验根目录（安全性）
   *   <li>调用 {@link SourceAdapter#discover(Path)} 发现候选会话项
   *   <li>对每个候选会话：定位源文件 → 读取 JSONL → 调用 {@link NormalizationEngine#normalize(String, List, List,
   *       List)} 归一化
   *   <li>将归一化制品写入 {@code --output-dir}
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
      // 1) 行级输入解析：每条输入都是一个独立 JSON 对象，不影响后续行
      input = mapper.readValue(line, BatchInputRecord.class);
    } catch (Exception e) {
      // 解析失败只报这一行错误，命令继续处理下一行
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
      // 2) 根据 sourceId 选择适配器，读取 rootPath 后启动该来源的候选发现
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
      // 安全兜底：如果根路径失败则不继续 discover，避免不可信路径触发扫描。
      writeOutput(
          mapper, new BatchOutputRecord("", "error", null, "Unsafe root path: " + rootPathStr));
      return;
    }

    var candidates = adapter.discover(rootPath);
    // 只要根目录可用，就按适配器顺序处理每个候选会话；单个候选失败不影响其他候选。
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
      // 1) 从 candidate 解析出源文件路径（locator 通常指向某个会话 session.jsonl）
      Path filePath = Path.of(candidate.fingerprint().locator());
      // 2) 按行读取原始会话事件，并记录解析级诊断（json 格式、字段缺失、未知事件等）
      JsonlReader jsonlReader = new JsonlReader();
      JsonlReaderResult readerResult = jsonlReader.read(filePath);
      List<JsonNode> events = readerResult.events();

      // 3) 构建本候选对应的源文件元数据；当前命令仅写入 transcript 角色
      NormalizedSourceFile sourceFile =
          new NormalizedSourceFile(
              "transcript",
              filePath.toAbsolutePath().toString(),
              Optional.empty(),
              Optional.empty());

      // 4) 调用归一化引擎：分类事件、重建通话/工具链、拼装统一会话 artifact
      String agent = adapter.sourceId().value();
      NormalizationEngine engine = new NormalizationEngine();
      var artifact =
          engine.normalize(agent, events, readerResult.diagnostics(), List.of(sourceFile));

      // 5) 将候选项指纹中的内容哈希透传到写入层，支持增量更新判断
      Map<String, String> fingerprints = buildFingerprints(filePath, candidate);

      // 6) 写入 normalized artifact（原子写入 data+meta；失败会抛异常）
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
