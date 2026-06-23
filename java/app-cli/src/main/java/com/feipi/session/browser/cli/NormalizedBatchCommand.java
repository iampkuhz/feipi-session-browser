package com.feipi.session.browser.cli;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.artifact.normalized.NormalizedArtifactWriter;
import com.feipi.session.browser.artifact.normalized.WriteResult;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.Callable;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * 隐藏的批量归一化子命令。
 *
 * <p><strong>用途</strong>：该命令用于"外部批处理入口"，供上游扫描管线（或脚本）调用；普通用户通常不会手工在终端直接使用它。它默认隐藏（{@code hidden =
 * true}），只在命令树中注册，不在 help 中展示。
 *
 * <p><strong>输入</strong>：从 stdin 按行读取 NDJSON，每行要求至少包含 {@code sourceId} 与 {@code rootPath}。可选包含
 * {@code requestId} 用于请求追踪。
 *
 * <p><strong>处理流程</strong>：逐行输入后，每个请求经过：
 *
 * <ol>
 *   <li>反序列化为 {@link BatchInputRecord}
 *   <li>通过 {@code sourceId} 解析适配器并校验根目录安全性
 *   <li>调用适配器发现会话候选项
 *   <li>对每个候选项调用 {@link SourceAdapter#parse} 执行 SPI 解析
 *   <li>读取源文件事件，调用 {@link NormalizationEngine#normalize} 归一化
 *   <li>将归一化制品写入 {@code --output-dir}
 * </ol>
 *
 * <p><strong>NDJSON 协议</strong>（stdout，仅在存在非空输入行时输出）：
 *
 * <ol>
 *   <li><strong>版本头</strong>：{@code {"protocol":"normalized-batch","version":"1.0"}}
 *   <li><strong>请求处理</strong>：每行输入对应一条 {@code {"type":"request",...}}
 *   <li><strong>逐候选结果</strong>：每个候选项对应一条 {@link BatchOutputRecord}
 *   <li><strong>结束摘要</strong>：{@code {"type":"end","totalRequests":...,...}}
 * </ol>
 *
 * <p><strong>组件复用</strong>：ObjectMapper、NormalizationEngine、NormalizedArtifactWriter、JsonlReader 在
 * batch 生命周期内各创建一次，不对每个候选项重建。
 *
 * <p><strong>退出码</strong>：仅协议级致命错误（如 stdout 序列化失败）返回非零；逐候选项或逐请求错误返回 0 并将错误详情写入协议输出。
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 JsonlReader、CallBuilder 等存在结构性相似 （语句级
 * STATEMENT_DUPLICATE），原因：均为 JSON/文件 IO 处理逻辑中的 null-safe 提取和 错误处理模式。此重复是 CLI 命令协调多个组件时的固有特征。
 */
@Command(
    name = "normalized-batch",
    description = "隐藏命令：批量归一化 session 并写入 artifact",
    hidden = true,
    mixinStandardHelpOptions = true)
final class NormalizedBatchCommand implements Callable<Integer> {

  private static final String PROTOCOL_VERSION = "1.0";

  @Option(
      names = {"--output-dir"},
      description = "artifact 输出目录",
      required = true)
  private Path outputDir;

  /** JSON 序列化器，batch 生命周期内复用。 */
  private ObjectMapper mapper;

  /** 归一化引擎，batch 生命周期内复用。 */
  private NormalizationEngine engine;

  /** 制品写入器，batch 生命周期内复用。 */
  private NormalizedArtifactWriter writer;

  /** JSONL 读取器，batch 生命周期内复用。 */
  private JsonlReader jsonlReader;

  /** 协议状态：是否已输出版本头。 */
  private boolean headerEmitted;

  /** 已处理的请求总数。 */
  private int requestCount;

  /**
   * 执行批量归一化流程。
   *
   * <p>初始化共享组件后逐行读取 stdin，处理完所有输入后输出结束摘要。组件（ObjectMapper、NormalizationEngine、
   * NormalizedArtifactWriter、JsonlReader）在整个 batch 生命周期内各创建一次。
   *
   * @return 退出码：0 表示正常完成（含逐候选错误），1 表示协议级致命错误
   * @throws Exception 当初始化失败时
   */
  @Override
  public Integer call() throws Exception {
    mapper = new ObjectMapper();
    engine = new NormalizationEngine();
    writer = new NormalizedArtifactWriter();
    jsonlReader = new JsonlReader();
    headerEmitted = false;
    requestCount = 0;

    Files.createDirectories(outputDir);

    boolean protocolBroken = false;

    try (BufferedReader reader =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        line = line.strip();
        if (line.isEmpty()) {
          continue;
        }
        try {
          processInputLine(line);
        } catch (Exception e) {
          // stdout 序列化失败等协议级错误，标记 broken pipe
          protocolBroken = true;
          break;
        }
      }
    }

    // 输出结束摘要（仅当协议已激活时）
    if (headerEmitted) {
      Map<String, Object> end = new LinkedHashMap<>();
      end.put("type", "end");
      end.put("totalRequests", requestCount);
      emitProtocolLine(end);
    }

    System.out.flush();
    return protocolBroken ? 1 : 0;
  }

  /**
   * 处理单行 NDJSON 输入。
   *
   * <p>解析输入行、校验必填字段、解析适配器、处理根目录下所有候选项。错误不向上抛出，而是以协议结果行输出。
   *
   * @param line 输入行
   */
  private void processInputLine(String line) {
    BatchInputRecord input;
    String requestId = null;
    try {
      input = mapper.readValue(line, BatchInputRecord.class);
      requestId = input.requestId();
      if (requestId == null || requestId.isBlank()) {
        requestId = generateRequestId();
      }
    } catch (Exception e) {
      requestId = generateRequestId();
      ensureHeader();
      emitRequest(requestId, null, null);
      emitResult(new BatchOutputRecord(requestId, "", "error", null, "Invalid input JSON", null));
      return;
    }

    if (input.sourceId() == null || input.rootPath() == null) {
      ensureHeader();
      emitRequest(requestId, input.sourceId(), input.rootPath());
      emitResult(
          new BatchOutputRecord(
              requestId, "", "error", null, "Missing sourceId or rootPath in input", null));
      return;
    }

    ensureHeader();
    emitRequest(requestId, input.sourceId(), input.rootPath());
    requestCount++;

    try {
      SourceAdapter adapter = SourceAdapterRegistry.forSourceId(input.sourceId());
      Path rootPath = Path.of(input.rootPath());
      processRootInput(adapter, rootPath, input.rootPath(), requestId);
    } catch (IllegalArgumentException e) {
      emitResult(new BatchOutputRecord(requestId, "", "error", null, sanitizeError(e), null));
    } catch (Exception e) {
      emitResult(new BatchOutputRecord(requestId, "", "error", null, sanitizeError(e), null));
    }
  }

  /**
   * 对单个源根执行安全检查和候选项处理。
   *
   * @param adapter 源适配器
   * @param rootPath 根目录路径
   * @param rootPathStr 原始根路径字符串（用于错误消息）
   * @param requestId 请求标识
   */
  private void processRootInput(
      SourceAdapter adapter, Path rootPath, String rootPathStr, String requestId) {
    SourceRoot root = adapter.checkRoot(rootPath);
    if (!root.isSafe()) {
      emitResult(new BatchOutputRecord(requestId, "", "error", null, "Unsafe root path", null));
      return;
    }

    var candidates = adapter.discover(rootPath);
    for (Candidate candidate : candidates.orderedItems()) {
      processCandidate(candidate, adapter, requestId);
    }
  }

  /**
   * 处理单个候选项：调用 adapter.parse → 读取 JSONL → 归一化 → 写入制品。
   *
   * <p>首先调用 {@link SourceAdapter#parse} 进行 SPI 级解析，获取诊断信息和解析状态。 然后根据解析状态决定是否继续执行归一化流程。
   *
   * @param candidate 待处理的候选项
   * @param adapter 源适配器
   * @param requestId 请求标识
   */
  private void processCandidate(Candidate candidate, SourceAdapter adapter, String requestId) {
    String sessionKey = candidate.sessionKey();
    try {
      // 1) 调用 adapter.parse 执行 SPI 级解析，获取诊断信息和解析状态
      SourceResult parseResult = adapter.parse(candidate, null);

      // 2) 处理非成功的解析状态
      if (parseResult instanceof SourceResult.Skipped skipped) {
        emitResult(
            new BatchOutputRecord(
                requestId, sessionKey, "skipped", null, sanitizeError(skipped.reason()), null));
        return;
      }
      if (parseResult instanceof SourceResult.Fatal fatal) {
        emitResult(
            new BatchOutputRecord(
                requestId, sessionKey, "error", null, sanitizeError(fatal.errorDetail()), null));
        return;
      }
      if (parseResult instanceof SourceResult.RetryableIncomplete retryable) {
        emitResult(
            new BatchOutputRecord(
                requestId, sessionKey, "error", null, sanitizeError(retryable.reason()), null));
        return;
      }

      // 3) 从 parse result 获取适配器级诊断（已包含 JSONL 读取诊断和语义诊断）
      List<SourceDiagnostic> diagnostics = parseResult.diagnostics();

      // 4) 读取 JSONL 获取 NormalizationEngine 所需的 JsonNode 事件列表
      //    adapter.parse 内部已完成读取，但 NormalizationEngine 接受 List<JsonNode>，
      //    ParsedRecord 不承载原始事件，因此此处需再次读取。
      Path filePath = Path.of(candidate.fingerprint().locator());
      JsonlReaderResult readerResult = jsonlReader.read(filePath);
      var events = readerResult.events();

      // 5) 构建源文件元数据
      NormalizedSourceFile sourceFile =
          new NormalizedSourceFile(
              "transcript",
              filePath.toAbsolutePath().toString(),
              Optional.empty(),
              Optional.empty());

      // 6) 调用归一化引擎
      String agent = adapter.sourceId().getValue();
      NormalizedSessionArtifact artifact =
          engine.normalize(agent, events, diagnostics, List.of(sourceFile));

      // 7) 构建源文件指纹映射
      Map<String, String> fingerprints = buildFingerprints(filePath, candidate);

      // 8) 写入 normalized artifact，获取实际文件路径
      WriteResult writeResult = writer.write(outputDir, artifact, fingerprints);

      // 9) 输出成功结果，artifactPath 为实际 data 文件路径
      emitResult(
          new BatchOutputRecord(
              requestId,
              sessionKey,
              "success",
              writeResult.dataPath().toString(),
              null,
              writeResult.contentHash()));
    } catch (Exception e) {
      emitResult(
          new BatchOutputRecord(requestId, sessionKey, "error", null, sanitizeError(e), null));
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

  // ===== 协议输出方法 =====

  /**
   * 确保协议版本头已输出。首次调用时输出版本头，后续调用无操作。
   *
   * <p>空输入不触发版本头输出，保证空输入测试的空 stdout 断言成立。
   */
  private void ensureHeader() {
    if (!headerEmitted) {
      Map<String, Object> header = new LinkedHashMap<>();
      header.put("protocol", "normalized-batch");
      header.put("version", PROTOCOL_VERSION);
      emitProtocolLine(header);
      headerEmitted = true;
    }
  }

  /**
   * 输出请求处理协议行。
   *
   * @param requestId 请求标识
   * @param sourceId 源标识，可能为 null
   * @param rootPath 根路径，可能为 null
   */
  private void emitRequest(String requestId, String sourceId, String rootPath) {
    Map<String, Object> req = new LinkedHashMap<>();
    req.put("type", "request");
    req.put("requestId", requestId);
    if (sourceId != null) {
      req.put("sourceId", sourceId);
    }
    if (rootPath != null) {
      req.put("rootPath", rootPath);
    }
    emitProtocolLine(req);
  }

  /**
   * 输出一条候选项结果协议行。
   *
   * @param record 结果记录
   */
  private void emitResult(BatchOutputRecord record) {
    try {
      System.out.println(mapper.writeValueAsString(record));
    } catch (Exception e) {
      // 序列化失败属于协议级致命错误，向上抛出以中断处理
      throw new RuntimeException("Output serialization failed", e);
    }
  }

  /**
   * 输出一条通用协议行。
   *
   * @param data 协议数据
   */
  private void emitProtocolLine(Object data) {
    try {
      System.out.println(mapper.writeValueAsString(data));
    } catch (Exception e) {
      throw new RuntimeException("Protocol serialization failed", e);
    }
  }

  // ===== 工具方法 =====

  /**
   * 生成请求标识。
   *
   * @return UUID 格式的请求标识
   */
  private static String generateRequestId() {
    return "req-" + UUID.randomUUID();
  }

  /**
   * 脱敏错误消息，去除绝对路径等敏感信息。
   *
   * @param e 异常
   * @return 脱敏后的错误消息
   */
  private String sanitizeError(Exception e) {
    return sanitizeError(e.getMessage());
  }

  /**
   * 脱敏错误消息，去除绝对路径等敏感信息。
   *
   * <p>将文件系统的绝对路径替换为仅文件名，防止泄露用户目录结构。
   *
   * @param message 原始错误消息
   * @return 脱敏后的错误消息
   */
  private static String sanitizeError(String message) {
    if (message == null || message.isBlank()) {
      return "Processing error";
    }
    // 替换绝对路径为仅文件名
    String sanitized = message.replaceAll("/[^\\s:'\"]+", "$0");
    sanitized = sanitized.replaceAll("(/[^/\\s:'\"]+/)+([^/\\s:'\"]+)", "$2");
    return sanitized;
  }
}
